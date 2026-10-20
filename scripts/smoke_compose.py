"""Test Docker isolé : image, authentification, écritures et persistance après recréation."""

import http.cookiejar
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path


def main():
    project = "lootsplit-smoke-" + secrets.token_hex(4)
    token = secrets.token_urlsafe(48)
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="lootsplit-smoke-") as directory:
        env = {
            **os.environ,
            "LOOTSPLIT_ADMIN_TOKEN": token,
            "LOOTSPLIT_SECURE_COOKIE": "false",
            "LOOTSPLIT_BANK_WEBSITE": "",
            "LOOTSPLIT_BANK_LOGIN": "",
            "LOOTSPLIT_BANK_PASSWORD": "",
            "LOOTSPLIT_BACKUP_ENABLED": "true",
            "LOOTSPLIT_BACKUP_TIME": "03:00",
            "LOOTSPLIT_BACKUP_TIMEZONE": "Europe/Paris",
            "APPDATA_PATH": Path(directory).as_posix(),
            "BIND_ADDRESS": "127.0.0.1",
            "PORT": "0",
            "PUID": "1000",
            "PGID": "1000",
        }

        def compose(*args, capture=False):
            return subprocess.run(
                ["docker", "compose", "-p", project, *args],
                cwd=root,
                env=env,
                check=True,
                text=True,
                capture_output=capture,
            ).stdout

        def request(path, body=None):
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(
                base + path,
                data=data,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.load(response)

        def wait_ready():
            nonlocal base
            port = compose("port", "lootsplit", "8000", capture=True).strip().rsplit(":", 1)[1]
            base = f"http://127.0.0.1:{port}"
            for _ in range(30):
                try:
                    if request("/health")["status"] == "ok":
                        return
                except (OSError, urllib.error.URLError):
                    time.sleep(0.5)
            raise RuntimeError("Le conteneur ne devient pas disponible.")

        base = ""
        try:
            compose("up", "-d", "--build")
            wait_ready()
            compose(
                "exec",
                "-T",
                "lootsplit",
                "python",
                "-c",
                "from woob.core import WoobBase; "
                "w=WoobBase(modules_path='/app/bank_modules'); "
                "assert w.modules_loader.get_or_load_module('cragr').klass.NAME == 'cragr'; "
                "w.deinit(); print('Module Woob cragr charge sans connexion bancaire.')",
            )
            assert not request("/api/banking/status")["configured"]
            with urllib.request.urlopen(base, timeout=10) as page:
                html = page.read().decode()
                assert '<div id="root"></div>' in html
                script = re.search(r'src="(/assets/[^\"]+\.js)"', html).group(1)
            with urllib.request.urlopen(base + script, timeout=10) as asset:
                assert asset.status == 200
            cookies = http.cookiejar.CookieJar()
            browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
            login = urllib.request.Request(
                base + "/api/auth/login",
                data=json.dumps({"token": token}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with browser.open(login, timeout=10) as response:
                csrf = json.load(response)["csrf_token"]
            session_request = urllib.request.Request(
                base + "/api/envelopes",
                data=json.dumps({"name": "Sécurité", "code": "RES-SECU"}).encode(),
                headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
            )
            with browser.open(session_request, timeout=10) as response:
                assert response.status == 201
            envelope_id = request("/api/envelopes", {"name": "Vacances", "code": "RES-VAC"})["id"]
            request(
                "/api/setup",
                {
                    "activation_date": (date.today() - timedelta(days=3)).isoformat(),
                    "opening_balance_cents": 100000,
                    "allocations": {str(envelope_id): 100000},
                },
            )
            day = (date.today() - timedelta(days=1)).isoformat()
            imported = request(
                "/api/import/csv",
                {
                    "content": f"booking_date;amount;raw_label\n{day};115,01;VIR RES-VAC\n",
                    "bank_balance_cents": 111501,
                },
            )
            assert imported["imported"] == 1 and imported["reconciliation"]["reconciled"]
            manual_backup = request("/api/backups", {})
            with urllib.request.urlopen(
                urllib.request.Request(
                    base + "/api/backups/" + manual_backup["name"] + "/download",
                    headers={"Authorization": f"Bearer {token}"},
                ),
                timeout=10,
            ) as saved:
                assert saved.read(16) == b"SQLite format 3\x00"
            for _ in range(45):
                backup_state = request("/api/backups")
                if backup_state["last_automatic_at"]:
                    break
                time.sleep(1)
            else:
                raise AssertionError("La sauvegarde automatique n'a pas été exécutée.")
            assert len([f for f in backup_state["files"] if f["kind"] == "daily"]) == 1
            assert len([f for f in backup_state["files"] if f["kind"] == "weekly"]) == 1
            compose(
                "exec",
                "-T",
                "lootsplit",
                "python",
                "-m",
                "lootsplit.backup",
                "--restore",
                "/data/backups/manual/" + manual_backup["name"],
                "--destination",
                "/data/restored-check",
            )
            compose(
                "exec",
                "-T",
                "lootsplit",
                "python",
                "-c",
                "import sqlite3; c=sqlite3.connect('/data/restored-check/app.db'); "
                "assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'; "
                "assert c.execute('SELECT COUNT(*) FROM bank_transactions').fetchone()[0] == 1; "
                "assert c.execute('SELECT SUM(amount_cents) FROM ledger').fetchone()[0] == 111501; "
                "c.close(); print('Restauration SQLite verifiee sur une copie isolee.')",
            )
            try:
                urllib.request.urlopen(base + "/api/accounts", timeout=5)
            except urllib.error.HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError("Une route métier est accessible sans jeton.")
            compose("exec", "-T", "lootsplit", "python", "-m", "lootsplit.backup")
            compose("up", "-d", "--force-recreate")
            wait_ready()
            reconciliation = request("/api/reconciliation")
            assert reconciliation["reconciled"]
            assert reconciliation["bank_balance_cents"] == 111501
            assert len(request("/api/transactions")) == 1
            assert request("/api/backups")["last_automatic_at"] == backup_state["last_automatic_at"]
            try:
                browser.open(base + "/api/auth/session", timeout=5)
            except urllib.error.HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError("Une session a survécu au redémarrage du serveur.")
            assert list(Path(directory).glob("backups/*.db"))
            print(
                "Docker Compose : interface, auth, import, sauvegardes automatiques, "
                "restauration et persistance OK."
            )
        finally:
            compose("down", "--remove-orphans")


if __name__ == "__main__":
    main()
