from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lootsplit.backup import backup
from lootsplit.domain import BankTransaction, BusinessError
from lootsplit.models import Allocation, AuditLog, LedgerEntry, Transaction
from lootsplit.service import LedgerService


def operation(amount=11500, label="VIR RES-NOEL", provider_id="bank-1", day=date(2026, 10, 5)):
    return BankTransaction(day, amount, label, provider_transaction_id=provider_id)


def test_initial_residual_and_reinitialization(ledger):
    svc, holidays, _ = ledger
    assert svc.balances()[holidays] == 80000
    assert svc.reconciliation()["unassigned_cents"] == 20000
    assert svc.reconciliation()["reconciled"]
    with pytest.raises(BusinessError):
        svc.initialize("Other", date(2026, 9, 30), 0, {})


def test_bank_entries_outgoing_interest_and_negative_envelope(ledger):
    svc, holidays, christmas = ledger
    result = svc.import_transactions(
        [
            operation(),
            operation(-90000, "VIR RES-VAC", "bank-2"),
            operation(14736, "INTÉRÊTS COMPTE DE RESERVE", "bank-3", date(2027, 1, 2)),
        ],
        "woob",
        36236,
    )
    assert result["imported"] == 3
    assert svc.balances()[christmas] == 11500
    assert svc.balances()[holidays] == -10000
    assert svc.reconciliation()["unassigned_cents"] == 34736
    assert svc.reconciliation()["reconciled"]
    assert svc.anomalies()["negative_envelope_ids"] == [holidays]
    assert len(svc.anomalies()["unassigned_transaction_ids"]) == 1


def test_correction_of_negative_transaction_keeps_bank_immutable(ledger):
    svc, holidays, christmas = ledger
    svc.import_transactions([operation(-15000, "UNKNOWN")], "woob", 85000)
    txn = svc.db.scalar(select(Transaction))
    original = (txn.amount_cents, txn.raw_label, txn.fingerprint)
    svc.correct_allocation(txn.id, holidays)
    assert svc.balances()[holidays] == 65000
    assert svc.reconciliation()["unassigned_cents"] == 20000
    svc.correct_allocation(txn.id, christmas)
    assert svc.balances()[holidays] == 80000
    assert svc.balances()[christmas] == -15000
    assert (txn.amount_cents, txn.raw_label, txn.fingerprint) == original
    assert svc.db.get(Allocation, txn.id).allocation_type == "MANUAL"
    assert svc.reconciliation()["reconciled"]
    assert (
        svc.db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type == "CORRECT_ALLOCATION")
        )
        == 2
    )
    count = svc.db.scalar(select(func.count()).select_from(LedgerEntry))
    svc.correct_allocation(txn.id, christmas)
    assert svc.db.scalar(select(func.count()).select_from(LedgerEntry)) == count


def test_reallocation_conserves_total_and_rejects_overdraft(ledger):
    svc, holidays, christmas = ledger
    before = svc.reconciliation()
    event_id = svc.reallocate(holidays, christmas, 20000, "Cadeaux")
    assert svc.balances()[holidays] == 60000
    assert svc.balances()[christmas] == 20000
    assert svc.reconciliation() == before
    entries = list(svc.db.scalars(select(LedgerEntry).where(LedgerEntry.event_id == event_id)))
    assert len(entries) == 2 and sum(e.amount_cents for e in entries) == 0
    for source, target, amount in (
        (holidays, christmas, 60001),
        (holidays, holidays, 1),
        (holidays, christmas, -1),
    ):
        with pytest.raises(BusinessError):
            svc.reallocate(source, target, amount)


def test_archive_requires_zero_and_old_code_goes_to_unassigned(ledger):
    svc, holidays, christmas = ledger
    with pytest.raises(BusinessError):
        svc.archive(holidays)
    svc.archive(christmas)
    svc.import_transactions([operation()], "woob", 111500)
    assert svc.balances().get(christmas, 0) == 0
    assert svc.reconciliation()["unassigned_cents"] == 31500
    with pytest.raises(BusinessError):
        svc.correct_allocation(1, christmas)
    with pytest.raises(BusinessError):
        svc.archive(svc.system_envelope().id)
    with pytest.raises(BusinessError):
        svc.edit_envelope(svc.system_envelope().id, {"name": "Other"})


def test_code_change_does_not_reassign_existing_transactions(ledger):
    svc, _, christmas = ledger
    svc.import_transactions([operation()], "woob", 111500)
    svc.edit_envelope(christmas, {"code": "RES-GIFTS"})
    svc.import_transactions([operation(), operation(provider_id="bank-2")], "woob", 123000)
    assert svc.balances()[christmas] == 11500
    assert svc.reconciliation()["unassigned_cents"] == 31500
    with pytest.raises(BusinessError):
        svc.create_envelope("Other", "res-gifts")


def test_repeated_import_and_cross_source_preserve_manual_allocation(ledger):
    svc, holidays, _ = ledger
    svc.import_transactions([operation()], "woob", 111500)
    svc.correct_allocation(1, holidays)
    for _ in range(10):
        assert svc.import_transactions([operation()], "woob", 111500)["duplicates"] == 1
    assert svc.import_transactions([operation(provider_id="csv-1")], "csv", 111500) == {
        "imported": 0,
        "duplicates": 1,
        "before_start": 0,
    }
    assert svc.db.scalar(select(func.count()).select_from(Transaction)) == 1
    assert svc.db.get(Allocation, 1).envelope_id == holidays
    assert svc.db.get(Allocation, 1).allocation_type == "MANUAL"


def test_distinct_stable_ids_preserve_identical_bank_transactions(ledger):
    svc, _, christmas = ledger
    svc.import_transactions([operation(), operation(provider_id="bank-2")], "woob", 123000)
    assert svc.balances()[christmas] == 23000
    assert len(svc.anomalies()["suspected_duplicate_fingerprints"]) == 1
    with pytest.raises(BusinessError, match="ambigu"):
        svc.import_transactions([operation(provider_id="csv-1")], "csv", 123000)


def test_identical_csv_lines_without_id_require_review(ledger):
    svc, _, _ = ledger
    with pytest.raises(BusinessError, match="ambigu"):
        svc.import_transactions([operation(provider_id=None)] * 2, "csv", 123000)
    assert svc.db.scalar(select(func.count()).select_from(Transaction)) == 0


def test_opening_cutoff_reconciliation_and_out_of_order_chart(ledger):
    svc, _, christmas = ledger
    result = svc.import_transactions(
        [
            operation(100, provider_id="later", day=date(2026, 12, 1)),
            operation(200, provider_id="earlier", day=date(2026, 10, 1)),
            operation(9999, provider_id="opening", day=date(2026, 9, 30)),
        ],
        "woob",
        100400,
    )
    assert result["before_start"] == 1
    assert svc.reconciliation()["difference_cents"] == 100
    chart = svc.chart(christmas, 2026)
    assert chart[0]["date"] == "2026-09-30"
    assert chart[1]["balance_cents"] == 200
    assert chart[-1]["balance_cents"] == 300
    assert svc.chart(christmas, 2025) == []


def test_immutable_database_records(ledger):
    svc, _, _ = ledger
    svc.import_transactions([operation()], "woob", 111500)
    for sql in (
        "UPDATE bank_transactions SET amount_cents=0",
        "DELETE FROM bank_transactions",
        "UPDATE ledger SET amount_cents=0",
        "DELETE FROM audit_log",
    ):
        with pytest.raises(IntegrityError):
            svc.db.execute(text(sql))


def test_failed_batch_rolls_back_balance_transactions_and_allocation(engine):
    with Session(engine) as session, session.begin():
        svc = LedgerService(session, today=date(2027, 1, 20))
        envelope = svc.create_envelope("Noël", "RES-NOEL")
        svc.initialize("Compte de réserve", date(2026, 9, 30), 100000, {envelope.id: 100000})
        svc.import_transactions([operation()], "woob", 111500)
    with pytest.raises(BusinessError, match="changé"):
        with Session(engine) as session, session.begin():
            svc = LedgerService(session, today=date(2027, 1, 20))
            svc.import_transactions(
                [
                    operation(500, provider_id="new"),
                    operation(99999),
                ],
                "woob",
                999999,
            )
    with Session(engine) as session:
        svc = LedgerService(session)
        assert session.scalar(select(func.count()).select_from(Transaction)) == 1
        assert svc.account().current_balance_cents == 111500
        assert svc.reconciliation()["reconciled"]


def test_backup_reads_committed_wal_data(engine, tmp_path):
    with Session(engine) as session, session.begin():
        LedgerService(session).create_envelope("Noël", "RES-NOEL")
    target = backup(tmp_path / "app.db", tmp_path / "backups")
    import sqlite3

    with sqlite3.connect(target) as db:
        assert db.execute("SELECT name FROM envelopes").fetchone()[0] == "Noël"
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_concurrent_reallocations_cannot_spend_the_same_balance_twice(engine):
    from concurrent.futures import ThreadPoolExecutor

    with Session(engine) as session, session.begin():
        svc = LedgerService(session)
        source = svc.create_envelope("Source", "RES-SRC").id
        target = svc.create_envelope("Cible", "RES-DST").id
        svc.initialize("Compte de réserve", date(2026, 9, 30), 10000, {source: 10000})

    def transfer():
        try:
            with Session(engine) as session, session.begin():
                LedgerService(session).reallocate(source, target, 8000)
            return "ok"
        except BusinessError:
            return "insufficient"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: transfer(), range(2)))
    assert sorted(outcomes) == ["insufficient", "ok"]
    with Session(engine) as session:
        svc = LedgerService(session)
        assert svc.balances()[source] == 2000
        assert svc.balances()[target] == 8000
        assert svc.reconciliation()["reconciled"]


def test_cross_source_alias_does_not_hide_second_identical_operation(ledger):
    svc, _, christmas = ledger
    svc.import_transactions([operation()], "csv", 111500)
    assert (
        svc.import_transactions([operation(provider_id="woob-1")], "woob", 111500)["duplicates"]
        == 1
    )
    result = svc.import_transactions(
        [operation(provider_id="woob-1"), operation(provider_id="woob-2")], "woob", 123000
    )
    assert result["imported"] == 1
    assert svc.balances()[christmas] == 23000
    assert svc.reconciliation()["reconciled"]


def test_domain_service_also_rejects_floating_point_money(ledger):
    svc, holidays, christmas = ledger
    with pytest.raises(BusinessError, match="entier"):
        svc.reallocate(holidays, christmas, 1.5)
    with pytest.raises(BusinessError, match="entier"):
        svc.import_transactions([], "csv", 100000.5)
