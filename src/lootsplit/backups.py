"""Sauvegardes quotidiennes, rotation bornée et statut indépendant des données métier."""

import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from lootsplit.backup import backup, copy_database
from lootsplit.domain import BusinessError

DAILY = re.compile(r"lootsplit-daily-(\d{4}-\d{2}-\d{2})\.db\Z")
WEEKLY = re.compile(r"lootsplit-weekly-(\d{4})-W(\d{2})\.db\Z")
MANUAL = re.compile(r"lootsplit-\d{8}T\d{12}Z\.db\Z")
ERROR = (
    "La sauvegarde a échoué. Vérifiez l'espace disponible et les droits du dossier de sauvegarde."
)


@dataclass(frozen=True)
class BackupConfiguration:
    enabled: bool = True
    time: str = "03:00"
    timezone: str = "Europe/Paris"

    def __post_init__(self):
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", self.time):
            raise ValueError("LOOTSPLIT_BACKUP_TIME doit être au format HH:MM.")
        ZoneInfo(self.timezone)

    @classmethod
    def from_environment(cls):
        enabled = os.getenv("LOOTSPLIT_BACKUP_ENABLED", "true").lower()
        if enabled not in {"true", "false"}:
            raise ValueError("LOOTSPLIT_BACKUP_ENABLED doit valoir true ou false.")
        return cls(
            enabled == "true",
            os.getenv("LOOTSPLIT_BACKUP_TIME", "03:00"),
            os.getenv("LOOTSPLIT_BACKUP_TIMEZONE", "Europe/Paris"),
        )


class Backups:
    def __init__(
        self,
        source: Path,
        directory: Path | None = None,
        configuration: BackupConfiguration | None = None,
        clock=None,
    ):
        self.source = source.resolve()
        self.directory = (directory or source.parent / "backups").resolve()
        self.configuration = configuration or BackupConfiguration.from_environment()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None
        self.retry_at = 0.0
        self.state = {}
        self._read_state()

    def _read_state(self):
        try:
            path = self.directory / "backup-state.json"
            if path.stat().st_size > 16_384:
                return
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                for key in ("last_success_at", "last_automatic_at"):
                    try:
                        stamp = datetime.fromisoformat(payload.get(key, ""))
                        if stamp.tzinfo is not None:
                            self.state[key] = stamp.astimezone(UTC).isoformat()
                    except (ValueError, TypeError):
                        pass
                try:
                    if self.state.get("last_automatic_at"):
                        self.state["last_automatic_date"] = date.fromisoformat(
                            payload.get("last_automatic_date", "")
                        ).isoformat()
                except (ValueError, TypeError):
                    pass
                self.state["last_error"] = ERROR if payload.get("last_error") else None
        except (OSError, ValueError):
            pass  # Un état absent/corrompu ne doit pas empêcher une nouvelle sauvegarde.

    def _write_state(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".state-", dir=self.directory)
        path = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(self.state, output)
                output.flush()
                os.fsync(output.fileno())
            path.replace(self.directory / "backup-state.json")
        finally:
            path.unlink(missing_ok=True)

    def _folder(self, kind: str) -> Path:
        path = self.directory / kind
        if path.is_symlink() or not path.resolve().is_relative_to(self.directory):
            raise ValueError("Dossier de sauvegarde non autorisé.")
        return path

    @staticmethod
    def _period(kind: str, name: str):
        try:
            if kind == "daily" and (match := DAILY.fullmatch(name)):
                return date.fromisoformat(match[1])
            if kind == "weekly" and (match := WEEKLY.fullmatch(name)):
                return date.fromisocalendar(int(match[1]), int(match[2]), 1)
            if kind in {"manual", "legacy"} and MANUAL.fullmatch(name):
                return datetime.strptime(name, "lootsplit-%Y%m%dT%H%M%S%fZ.db").date()
        except ValueError:
            return None
        return None

    def files(self):
        result = []
        for kind in ("daily", "weekly", "manual", "legacy"):
            folder = self.directory if kind == "legacy" else self._folder(kind)
            if not folder.is_dir():
                continue
            for path in folder.iterdir():
                if path.is_symlink() or not path.is_file() or self._period(kind, path.name) is None:
                    continue
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    continue
                result.append(
                    {
                        "name": path.name,
                        "kind": kind,
                        "size_bytes": stat.st_size,
                        "created_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                    }
                )
        return sorted(result, key=lambda item: item["created_at"], reverse=True)

    def download_path(self, name: str) -> Path:
        # Le nom doit être l'une des copies générées et recensées ; aucun chemin libre.
        for item in self.files():
            if item["name"] == name:
                folder = self.directory if item["kind"] == "legacy" else self._folder(item["kind"])
                path = folder / name
                if path.is_symlink() or path.resolve().parent != folder.resolve():
                    break
                return path
        raise BusinessError("Sauvegarde introuvable.")

    def _slot(self, day: date):
        hour, minute = map(int, self.configuration.time.split(":"))
        local = datetime(
            day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(self.configuration.timezone)
        )
        # Au changement d'heure, un horaire inexistant est reporté après le saut.
        return local.astimezone(UTC).astimezone(local.tzinfo)

    def _due(self, now: datetime):
        local = now.astimezone(ZoneInfo(self.configuration.timezone))
        if self.state.get("last_automatic_date") == local.date().isoformat():
            path = self.directory / "daily" / f"lootsplit-daily-{local.date().isoformat()}.db"
            return not (path.is_file() and not path.is_symlink())
        today_slot = self._slot(local.date())
        last = self.state.get("last_automatic_at")
        if not last:
            return True  # Première copie au démarrage, sans attendre la nuit suivante.
        try:
            last_time = datetime.fromisoformat(last).astimezone(UTC)
        except (ValueError, TypeError):
            return True
        due_slot = (
            today_slot if local >= today_slot else self._slot(local.date() - timedelta(days=1))
        )
        return last_time < due_slot.astimezone(UTC)

    def status(self):
        now = self.clock()
        next_backup = None
        if self.configuration.enabled:
            local = now.astimezone(ZoneInfo(self.configuration.timezone))
            if self._due(now):
                next_backup = now
            else:
                day = local.date()
                if (
                    local >= self._slot(day)
                    or self.state.get("last_automatic_date") == day.isoformat()
                ):
                    day += timedelta(days=1)
                next_backup = self._slot(day)
        try:
            items = self.files()
            error = self.state.get("last_error")
        except (OSError, ValueError):
            items, error = [], ERROR
        if next_backup and self.retry_at > time.monotonic():
            retry = now + timedelta(seconds=self.retry_at - time.monotonic())
            next_backup = max(next_backup, retry)
        return {
            "enabled": self.configuration.enabled,
            "time": self.configuration.time,
            "timezone": self.configuration.timezone,
            "daily_retention": 7,
            "weekly_retention": 4,
            "running": self.lock.locked(),
            "last_success_at": self.state.get("last_success_at"),
            "last_automatic_at": self.state.get("last_automatic_at"),
            "last_error": error,
            "next_backup_at": next_backup.isoformat() if next_backup else None,
            "files": items,
        }

    def _rotate(self, kind: str, keep: int):
        folder = self._folder(kind)
        candidates = [
            (self._period(kind, path.name), path)
            for path in folder.iterdir()
            if path.is_file() and not path.is_symlink()
        ]
        candidates = sorted((day, path) for day, path in candidates if day is not None)
        for _, path in candidates[:-keep]:
            # Uniquement nos noms dans le dossier dédié ; jamais les copies manuelles.
            path.unlink()

    def _automatic(self, now: datetime):
        day = now.astimezone(ZoneInfo(self.configuration.timezone)).date()
        daily = self._folder("daily") / f"lootsplit-daily-{day.isoformat()}.db"
        copy_database(self.source, daily)
        year, week, _ = day.isocalendar()
        weekly = self._folder("weekly") / f"lootsplit-weekly-{year}-W{week:02}.db"
        if weekly.is_symlink():
            raise ValueError("Fichier de sauvegarde non autorisé.")
        if not weekly.exists():
            copy_database(daily, weekly)
        self._rotate("daily", 7)
        self._rotate("weekly", 4)
        self.state["last_automatic_at"] = now.isoformat()
        self.state["last_automatic_date"] = day.isoformat()
        return daily

    def create(self, automatic=False):
        if not self.lock.acquire(blocking=False):
            raise BusinessError("Une sauvegarde est déjà en cours.")
        previous_state = self.state.copy()
        try:
            now = self.clock()
            target = (
                self._automatic(now) if automatic else backup(self.source, self._folder("manual"))
            )
            self.state["last_success_at"] = now.isoformat()
            self.state["last_error"] = None
            self._write_state()
            self.retry_at = 0.0
            return {"name": target.name, "kind": "daily" if automatic else "manual"}
        except Exception:
            self.state = previous_state
            self.state["last_error"] = ERROR
            self.retry_at = time.monotonic() + 3600
            try:
                self._write_state()
            except OSError:
                pass
            raise BusinessError(ERROR) from None
        finally:
            self.lock.release()

    def run_due(self):
        if (
            self.configuration.enabled
            and time.monotonic() >= self.retry_at
            and not self.lock.locked()
            and self._due(self.clock())
        ):
            return self.create(automatic=True)
        return None

    def start(self):
        def loop():
            while not self.stop.wait(30):
                try:
                    self.run_due()
                except Exception:
                    continue  # Le statut conserve l'erreur sans détails de chemin ou de données.

        self.thread = threading.Thread(target=loop, daemon=True, name="sqlite-backups")
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
