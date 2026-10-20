import sqlite3
from contextlib import closing

from fastapi.testclient import TestClient

from lootsplit.api import create_app

TOKEN = "backups-testing-key-with-more-than-thirty-two-characters"


def test_backup_api_protected_download_and_persisted_status(tmp_path):
    app = create_app(tmp_path / "app.db", TOKEN)
    with TestClient(app) as browser:
        assert browser.get("/api/backups").status_code == 401
        assert browser.post("/api/backups").status_code == 401
        login = browser.post("/api/auth/login", json={"token": TOKEN}).json()
        assert browser.post("/api/backups").status_code == 403
        created = browser.post("/api/backups", headers={"X-CSRF-Token": login["csrf_token"]})
        assert created.status_code == 201
        name = created.json()["name"]
        state = browser.get("/api/backups").json()
        assert state["daily_retention"] == 7 and state["weekly_retention"] == 4
        assert state["files"][0]["name"] == name
        response = browser.get(f"/api/backups/{name}/download")
        assert response.status_code == 200
        assert response.content.startswith(b"SQLite format 3\x00")
        assert response.headers["cache-control"] == "no-store"
        assert "attachment" in response.headers["content-disposition"]
        downloaded = tmp_path / "downloaded.db"
        downloaded.write_bytes(response.content)
        with closing(sqlite3.connect(downloaded)) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert browser.get("/api/backups/app.db/download").status_code == 409
        browser.cookies.clear()
        assert browser.get(f"/api/backups/{name}/download").status_code == 401
    with TestClient(
        create_app(tmp_path / "app.db", TOKEN), headers={"Authorization": f"Bearer {TOKEN}"}
    ) as browser:
        assert browser.get("/api/backups").json()["last_success_at"] == state["last_success_at"]
