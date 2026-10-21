from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lootsplit.connectors import CsvConnector
from lootsplit.domain import BankTransaction, BusinessError
from lootsplit.models import Transaction
from lootsplit.service import LedgerService
from lootsplit.sync import synchronize


def test_csv_bom_quotes_exact_cents_and_cutoff():
    connector = CsvConnector(
        '\ufeffbooking_date;amount;raw_label\n2026-10-01;147,36;"INTÉRÊTS; Compte de réserve"\n',
        14736,
    )
    assert connector.get_accounts()[0].id == "1"
    assert connector.get_balance("1") == 14736
    assert connector.get_transactions("1", date(2026, 9, 30))[0].amount_cents == 14736
    assert connector.get_transactions("1", date(2026, 10, 1)) == []
    with pytest.raises(BusinessError):
        connector.get_balance("other")


@pytest.mark.parametrize(
    "content",
    [
        '"unfinished header',
        "booking_date;amount;raw_label;amount\n2026-10-01;10;VIR;20",
        "date;montant;libelle\n2026-10-01;10;VIR",
        "booking_date;amount;raw_label\n2026-10-01;10;VIR;EXTRA",
        "booking_date;amount;raw_label\n2026-10-01;10",
        "booking_date;amount;raw_label\n2026-10-01;1,001;VIR",
    ],
)
def test_invalid_csv(content):
    with pytest.raises(BusinessError):
        CsvConnector(content, 0)


def test_sync_failure_keeps_existing_data_and_success_time(engine):
    start = date(2026, 9, 30)
    with Session(engine) as session, session.begin():
        svc = LedgerService(session)
        envelope = svc.create_envelope("Vacances", "RES-VAC")
        svc.initialize("Compte de réserve", start, 10000, {envelope.id: 10000})

    class Connector:
        source = "fake"
        fail = False

        def get_balance(self, account_id):
            return 11000

        def get_transactions(self, account_id, since):
            assert since == start
            if self.fail:
                raise RuntimeError("bank_password=secret")
            return [BankTransaction(date(2026, 10, 1), 1000, "RES-VAC")]

    connector = Connector()
    assert synchronize(engine, connector, "1")["imported"] == 1
    with Session(engine) as session:
        last_sync = LedgerService(session).account().last_sync_at
    connector.fail = True
    with pytest.raises(BusinessError, match="conservées"):
        synchronize(engine, connector, "1")
    with Session(engine) as session:
        svc = LedgerService(session)
        assert svc.account().last_sync_at == last_sync
        assert svc.account().current_balance_cents == 11000
        assert "secret" not in svc.account().last_sync_error
        assert session.scalar(select(func.count()).select_from(Transaction)) == 1
        assert svc.reconciliation()["reconciled"]
