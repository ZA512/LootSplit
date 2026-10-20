import sqlite3

from sqlalchemy.orm import Session

from lootsplit.database import create_database
from lootsplit.models import Envelope
from lootsplit.service import LedgerService


def test_previous_database_is_backed_up_and_adopted_without_losing_data(tmp_path):
    path = tmp_path / "app.db"
    engine = create_database(path)
    with Session(engine) as session, session.begin():
        LedgerService(session).create_envelope("Sécurité", "RES-SECU")
    engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE bank_connection")
        db.execute("PRAGMA user_version=0")
    upgraded = create_database(path)
    with Session(upgraded) as session:
        assert session.get(Envelope, 1).name == "Sécurité"
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    saved = list((tmp_path / "backups" / "before-migration").glob("*.db"))
    assert len(saved) == 1
    with sqlite3.connect(saved[0]) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
        assert db.execute("SELECT name FROM envelopes").fetchone()[0] == "Sécurité"
    upgraded.dispose()
