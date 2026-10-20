import io
import json
import subprocess
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from woob.capabilities.bank import Account as WoobAccount
from woob.capabilities.bank import Transaction as WoobTransaction
from woob.capabilities.base import NotAvailable
from woob.exceptions import ActionNeeded, BrowserIncorrectPassword

from lootsplit.banking import Banking, utc_now
from lootsplit.domain import BankTransaction, BusinessError
from lootsplit.models import Account, BankConnection, Transaction
from lootsplit.service import LedgerService
from lootsplit.woob_connector import BankConfiguration, ConnectorError, WoobConnector
from lootsplit.woob_worker import collect, euro_cents, main


def bank_account(identifier="bank-account-1", label="Livret A", kind=WoobAccount.TYPE_SAVINGS):
    account = WoobAccount(identifier)
    account.label = label
    account.type = kind
    account.currency = "EUR"
    account.balance = Decimal("1115.01")
    account.iban = "FR7612345678901234567890123"
    return account


def bank_transaction(identifier, amount, booked, label="RES-VAC"):
    transaction = WoobTransaction(identifier)
    transaction.date = booked
    transaction.amount = Decimal(amount)
    transaction.raw = label
    return transaction


def test_adapter_maps_woob_objects_and_reads_only_booked_livret_history():
    account = bank_account()
    last = date(2026, 10, 5)
    transactions = [
        bank_transaction("newer", "115.01", last),
        bank_transaction("old", "1.00", date(2026, 9, 30)),
        bank_transaction("older", "-15.01", date(2026, 10, 1)),
    ]

    class Backend:
        def iter_accounts(self):
            return [
                account,
                bank_account("checking", "Compte courant", WoobAccount.TYPE_CHECKING),
                bank_account("ldd", "LDD"),
            ]

        def iter_history(self, selected):
            assert selected is account
            return transactions

        def iter_coming(self, *_):
            raise AssertionError("Les opérations à venir ne doivent pas être lues.")

    discovered = collect(Backend(), {"operation": "accounts"})
    assert len(discovered) == 1
    assert discovered[0]["masked_iban"] == "•••• 0123"
    assert account.iban not in json.dumps(discovered[0]["masked_iban"])
    snapshot = collect(
        Backend(), {"operation": "snapshot", "account_id": account.id, "since": "2026-09-30"}
    )
    assert snapshot["balance_cents"] == 111501
    assert [t["amount_cents"] for t in snapshot["transactions"]] == [11501, -1501]
    assert snapshot["transactions"][0]["value_date"] is None
    with pytest.raises(ConnectorError, match="sélectionné"):
        collect(Backend(), {"operation": "snapshot", "account_id": "wrong", "since": "2026-09-30"})


@pytest.mark.parametrize("value", [1.23, True, NotAvailable, Decimal("NaN"), Decimal("0.001")])
def test_no_approximate_or_missing_bank_money(value):
    with pytest.raises(BusinessError):
        euro_cents(value)


@pytest.fixture
def configuration(tmp_path):
    (tmp_path / "cragr").mkdir()
    (tmp_path / "cragr" / "module.py").touch()
    return BankConfiguration("www.ca-paris.fr", "12345678901", "123456", tmp_path)


def test_worker_isolated_no_secrets_in_arguments_and_single_snapshot(configuration, monkeypatch):
    calls = []

    def run(command, **kwargs):
        assert "123456" not in " ".join(command)
        payload = json.loads(kwargs["input"])
        assert payload["password"] == "123456"
        assert kwargs["timeout"] == 180
        calls.append(payload)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "data": {
                        "balance_cents": 111501,
                        "transactions": [
                            {
                                "booking_date": "2026-10-05",
                                "value_date": None,
                                "amount_cents": 11501,
                                "raw_label": "RES-VAC",
                                "provider_transaction_id": "1",
                            }
                        ],
                    },
                }
            ),
        )

    monkeypatch.setattr(subprocess, "run", run)
    connector = WoobConnector(configuration, date(2026, 9, 30))
    assert connector.get_balance("bank-1") == 111501
    assert connector.get_transactions("bank-1", date(2026, 9, 30))[0].amount_cents == 11501
    assert len(calls) == 1
    with pytest.raises(ConnectorError):
        connector.get_transactions("bank-2", date(2026, 9, 30))


def test_worker_timeout_is_sanitized(configuration, monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(["secret"], 180, output="secret")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ConnectorError) as error:
        WoobConnector(configuration, date(2026, 9, 30)).get_balance("bank-1")
    assert error.value.code == "timeout" and "secret" not in str(error.value)


@pytest.mark.parametrize(
    "exception,code",
    [
        (ActionNeeded("bank_password=secret"), "action_required"),
        (BrowserIncorrectPassword("bank_password=secret"), "credentials"),
        (RuntimeError("bank_password=secret"), "unavailable"),
    ],
)
def test_worker_never_emits_provider_exception_or_debug_output(
    monkeypatch, capsys, exception, code
):
    import lootsplit.woob_worker as worker

    def fail(_):
        print("bank_password=secret")
        raise exception

    monkeypatch.setattr(worker, "execute", fail)
    monkeypatch.setattr(worker.sys, "stdin", io.StringIO("{}"))
    main()
    result = capsys.readouterr()
    assert json.loads(result.out) == {"ok": False, "error": code}
    assert "secret" not in result.out + result.err


def test_secrets_can_be_read_from_files_without_exposing_repr(tmp_path, monkeypatch):
    password = tmp_path / "secret"
    password.write_text("123456\n")
    monkeypatch.setenv("LOOTSPLIT_BANK_PASSWORD_FILE", str(password))
    config = BankConfiguration.from_environment()
    assert config.password == "123456"
    assert "123456" not in repr(config)


@pytest.mark.skipif(
    not Path("bank_modules/cragr/module.py").is_file(),
    reason="Le module local est installé par le build Docker ou le script dédié.",
)
def test_real_module_rejects_invalid_configuration_before_any_network_access(monkeypatch):
    import requests

    from lootsplit.woob_worker import execute

    def no_network(*args, **kwargs):
        raise AssertionError("Aucune requête bancaire ne doit être effectuée.")

    monkeypatch.setattr(requests.Session, "request", no_network)
    with pytest.raises(ConnectorError) as error:
        execute(
            {
                "operation": "accounts",
                "modules_path": str(Path("bank_modules").resolve()),
                "website": "invalid.invalid",
                "login": "bad",
                "password": "bad",
            }
        )
    assert error.value.code == "configuration"


@pytest.fixture
def banking(engine, configuration):
    with Session(engine) as session, session.begin():
        svc = LedgerService(session)
        envelope = svc.create_envelope("Vacances", "RES-VAC")
        svc.initialize("Livret A", date(2026, 9, 30), 100000, {envelope.id: 100000})

    class Connector:
        source = "woob"
        error = None

        def __init__(self, config, since=None):
            self.since = since

        def discover(self):
            return [
                {
                    "id": "real-private-account-id",
                    "name": "Livret A",
                    "balance_cents": 111501,
                    "masked_iban": "•••• 0123",
                }
            ]

        def get_balance(self, account_id):
            assert account_id == "real-private-account-id"
            if self.error:
                raise ConnectorError(self.error)
            return 111501

        def get_transactions(self, account_id, since):
            return [
                BankTransaction(
                    date(2026, 10, 5), 11501, "RES-VAC", provider_transaction_id="bank-1"
                )
            ]

    return Banking(engine, configuration, Connector)


def connect(banking):
    choice = banking.discover()[0]
    assert "real-private" not in json.dumps(choice)
    banking.select(choice["choice_id"], True, "ADMIN")


def test_selection_requires_confirmation_and_cannot_change_underlying_account(banking):
    choice = banking.discover()[0]
    with pytest.raises(BusinessError, match="Confirmez"):
        banking.select(choice["choice_id"], False, "ADMIN")
    banking.select(choice["choice_id"], True, "ADMIN")
    assert banking.status()["connected"]
    assert not banking.status()["auto_sync_enabled"]
    banking.choices["another"] = (float("inf"), {"id": "different"})
    with pytest.raises(BusinessError, match="autre"):
        banking.select("another", True, "ADMIN")


def test_bank_sync_schedule_cooldown_and_preserved_manual_allocation(banking, engine):
    connect(banking)
    banking.configure_schedule(True, 6, "ADMIN")
    assert banking.sync()["imported"] == 1
    assert banking.status()["last_success_at"].endswith("Z")
    with pytest.raises(BusinessError, match="minute"):
        banking.sync()
    with Session(engine) as session, session.begin():
        svc = LedgerService(session)
        svc.correct_allocation(1, svc.system_envelope().id)
        connection = session.get(BankConnection, 1)
        connection.last_attempt_at -= timedelta(minutes=2)
    assert banking.sync()["duplicates"] == 1
    with Session(engine) as session:
        svc = LedgerService(session)
        assert svc.reconciliation()["unassigned_cents"] == 11501
        assert svc.reconciliation()["reconciled"]


def test_authentication_failure_pauses_automatic_retries_without_data_loss(banking, engine):
    connect(banking)
    banking.configure_schedule(True, 6, "ADMIN")
    banking.sync()
    with Session(engine) as session, session.begin():
        connection = session.get(BankConnection, 1)
        connection.last_attempt_at -= timedelta(minutes=2)
        previous_success = connection.last_success_at
    banking.factory.error = "action_required"
    with pytest.raises(ConnectorError):
        banking.sync()
    status = banking.status()
    assert status["automatic_paused"] and status["error_code"] == "action_required"
    with Session(engine) as session, session.begin():
        assert session.get(Account, 1).current_balance_cents == 111501
        assert session.scalar(select(func.count()).select_from(Transaction)) == 1
        connection = session.get(BankConnection, 1)
        assert connection.last_success_at == previous_success
        connection.next_sync_at = utc_now() - timedelta(seconds=1)
    banking.run_due()  # Ne déclenche pas de nouvel appel pendant l'action requise.
    with Session(engine) as session, session.begin():
        svc = LedgerService(session)
        svc.import_transactions([], "csv", 111501)
        assert svc.reconciliation()["last_sync_error"] is not None


def test_due_sync_and_no_overlap(banking, engine):
    connect(banking)
    banking.configure_schedule(True, 6, "ADMIN")
    banking.run_due()
    with Session(engine) as session, session.begin():
        assert session.get(BankConnection, 1).last_success_at is None
        session.get(BankConnection, 1).next_sync_at = utc_now() - timedelta(seconds=1)
    with banking.lock:
        assert banking.sync(manual=False) is None
        with pytest.raises(BusinessError, match="en cours"):
            banking.discover()
    banking.run_due()
    assert banking.status()["last_success_at"] is not None


def test_interruption_reserves_next_automatic_attempt_without_importing(
    banking, engine, monkeypatch
):
    connect(banking)
    banking.configure_schedule(True, 6, "ADMIN")

    def interrupt(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(banking.factory, "get_balance", interrupt)
    with pytest.raises(KeyboardInterrupt):
        banking.sync()
    with Session(engine) as session:
        connection = session.get(BankConnection, 1)
        assert connection.next_sync_at > utc_now() + timedelta(hours=5)
        assert connection.last_success_at is None
        assert session.get(Account, 1).current_balance_cents == 100000
        assert session.scalar(select(func.count()).select_from(Transaction)) == 0
    banking.run_due()  # L'échéance réservée empêche un nouvel accès après interruption.
