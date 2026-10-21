from datetime import date

import pytest
from sqlalchemy.orm import Session

from lootsplit.database import create_database
from lootsplit.service import LedgerService


@pytest.fixture(autouse=True)
def no_real_bank_credentials(monkeypatch):
    monkeypatch.setenv("LOOTSPLIT_BACKUP_ENABLED", "false")
    # Un poste configuré pour la banque doit pouvoir exécuter les tests hors ligne.
    for name in (
        "LOOTSPLIT_BANK_WEBSITE",
        "LOOTSPLIT_BANK_LOGIN",
        "LOOTSPLIT_BANK_PASSWORD",
        "LOOTSPLIT_BANK_LOGIN_FILE",
        "LOOTSPLIT_BANK_PASSWORD_FILE",
        "LOOTSPLIT_BACKUP_PATH",
        "LOOTSPLIT_BACKUP_TIME",
        "LOOTSPLIT_BACKUP_TIMEZONE",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def engine(tmp_path):
    engine = create_database(tmp_path / "app.db")
    yield engine
    engine.dispose()


@pytest.fixture
def ledger(engine):
    with Session(engine) as session, session.begin():
        svc = LedgerService(session, today=date(2027, 1, 20))
        holidays = svc.create_envelope("Vacances", "RES-VAC")
        christmas = svc.create_envelope("Noël", "RES-NOEL")
        svc.initialize("Compte de réserve", date(2026, 9, 30), 100_000, {holidays.id: 80_000})
        yield svc, holidays.id, christmas.id
