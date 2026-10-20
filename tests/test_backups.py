import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

import lootsplit.backups as scheduling
from lootsplit.backup import backup, copy_database, restore
from lootsplit.backups import BackupConfiguration, Backups
from lootsplit.database import create_database
from lootsplit.domain import BankTransaction, BusinessError
from lootsplit.models import BankConnection
from lootsplit.service import LedgerService


@pytest.fixture
def populated(engine, tmp_path):
    with Session(engine) as session, session.begin():
        svc = LedgerService(session)
        vacation = svc.create_envelope("Vacances", "RES-VAC").id
        safety = svc.create_envelope("Sécurité", "RES-SECU").id
        svc.initialize(
            "Livret A", datetime(2026, 9, 30).date(), 40000, {vacation: 30000, safety: 10000}
        )
        svc.import_transactions(
            [
                BankTransaction(datetime(2026, 10, 1).date(), 11501, "RES-VAC"),
                BankTransaction(datetime(2026, 10, 2).date(), 14736, "INTÉRÊTS"),
            ],
            "csv",
            66237,
        )
        svc.correct_allocation(2, safety)
        svc.reallocate(vacation, safety, 2000, "Répartition familiale")
        session.add(
            BankConnection(
                id=1,
                provider_account_id="private-account",
                masked_iban="•••• 4321",
                auto_sync_enabled=False,
            )
        )
    return tmp_path / "app.db"


def manager(source, directory, clock, enabled=True, at="03:00"):
    return Backups(
        source, directory, BackupConfiguration(enabled, at, "Europe/Paris"), clock=lambda: clock[0]
    )


def test_live_wal_snapshot_can_be_restored_with_history_audit_and_bank_settings(
    populated, tmp_path
):
    target = backup(populated, tmp_path / "snapshots")
    restored = restore(target, tmp_path / "restored")
    with closing(sqlite3.connect(restored)) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT COUNT(*) FROM bank_transactions").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] >= 5
        assert (
            db.execute("SELECT provider_account_id FROM bank_connection").fetchone()[0]
            == "private-account"
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE bank_transactions SET amount_cents=0")
    assert not list((tmp_path / "restored").glob("*-wal"))
    reopened = create_database(restored)
    with Session(reopened) as session:
        svc = LedgerService(session)
        assert svc.reconciliation()["reconciled"]
        assert svc.balances()[1] == 39501
        assert svc.balances()[2] == 26736
    reopened.dispose()


def test_corrupt_source_never_replaces_a_good_snapshot(populated, tmp_path):
    target = backup(populated, tmp_path / "backups")
    previous = target.read_bytes()
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"this is not sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        copy_database(corrupt, target)
    assert target.read_bytes() == previous
    assert not list(target.parent.glob("*.partial"))
    with pytest.raises(ValueError, match="distincte"):
        copy_database(populated, populated)


def test_restore_refuses_existing_directory_and_unrelated_or_future_database(populated, tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    protected = existing / "app.db"
    protected.write_bytes(b"do not replace")
    with pytest.raises(FileExistsError):
        restore(populated, existing)
    assert protected.read_bytes() == b"do not replace"
    other = tmp_path / "other.db"
    with closing(sqlite3.connect(other)) as db:
        db.execute("CREATE TABLE unrelated (id INTEGER)")
        db.commit()
    with pytest.raises(ValueError, match="complète"):
        restore(other, tmp_path / "invalid-restore")
    assert not (tmp_path / "invalid-restore").exists()
    future = backup(populated, tmp_path / "future")
    with closing(sqlite3.connect(future)) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="version"):
        restore(future, tmp_path / "future-restore")


def test_rotation_keeps_seven_days_four_weeks_and_preserves_manual_and_migration_copies(
    populated, tmp_path
):
    clock = [datetime(2026, 12, 1, 4, tzinfo=UTC)]
    service = manager(populated, tmp_path / "backups", clock)
    manual = service.create()
    migration = backup(populated, tmp_path / "backups" / "before-migration")
    legacy = backup(populated, tmp_path / "backups")
    unrelated = tmp_path / "backups" / "daily" / "personal-notes.txt"
    unrelated.parent.mkdir()
    unrelated.write_text("keep")
    for _ in range(45):
        service.run_due()
        clock[0] += timedelta(days=1)
    status = service.status()
    daily = [f for f in status["files"] if f["kind"] == "daily"]
    weekly = [f for f in status["files"] if f["kind"] == "weekly"]
    assert len(daily) == 7 and len(weekly) == 4
    assert daily[0]["name"] == "lootsplit-daily-2027-01-14.db"
    assert {f["name"] for f in weekly} == {
        "lootsplit-weekly-2026-W52.db",
        "lootsplit-weekly-2026-W53.db",
        "lootsplit-weekly-2027-W01.db",
        "lootsplit-weekly-2027-W02.db",
    }
    assert service.download_path(manual["name"]).is_file()
    assert migration.is_file() and legacy.is_file() and unrelated.read_text() == "keep"


def test_restart_no_double_backup_and_offline_catchup_without_backdating(populated, tmp_path):
    clock = [datetime(2026, 10, 20, 10, tzinfo=UTC)]
    directory = tmp_path / "backups"
    first = manager(populated, directory, clock)
    first.run_due()
    daily = first.download_path("lootsplit-daily-2026-10-20.db")
    previous = daily.stat().st_mtime_ns
    restarted = manager(populated, directory, clock)
    assert restarted.run_due() is None
    assert daily.stat().st_mtime_ns == previous
    clock[0] += timedelta(days=8)
    restarted.run_due()
    names = [item["name"] for item in restarted.files() if item["kind"] == "daily"]
    assert sorted(names) == ["lootsplit-daily-2026-10-20.db", "lootsplit-daily-2026-10-28.db"]


@pytest.mark.parametrize(
    "start,next_utc,at",
    [
        (datetime(2026, 3, 28, 4, tzinfo=UTC), datetime(2026, 3, 29, 1, tzinfo=UTC), "03:00"),
        (datetime(2026, 3, 28, 4, tzinfo=UTC), datetime(2026, 3, 29, 1, 30, tzinfo=UTC), "02:30"),
        (datetime(2026, 10, 24, 4, tzinfo=UTC), datetime(2026, 10, 25, 0, 30, tzinfo=UTC), "02:30"),
    ],
)
def test_schedule_follows_paris_daylight_saving_time(populated, tmp_path, start, next_utc, at):
    clock = [start]
    service = manager(populated, tmp_path / "backups", clock, at=at)
    service.run_due()
    assert datetime.fromisoformat(service.status()["next_backup_at"]).astimezone(UTC) == next_utc
    clock[0] = next_utc - timedelta(seconds=1)
    assert service.run_due() is None
    clock[0] = next_utc + timedelta(seconds=1)
    assert service.run_due() is not None
    clock[0] += timedelta(hours=1)
    assert service.run_due() is None


def test_failure_preserves_previous_files_and_retries_later_without_leaking_paths(
    populated, tmp_path, monkeypatch
):
    clock = [datetime(2026, 10, 20, 4, tzinfo=UTC)]
    service = manager(populated, tmp_path / "backups", clock)
    service.run_due()
    previous = service.files()
    clock[0] += timedelta(days=1)

    def full_disk(*_args, **_kwargs):
        raise OSError("secret-server-path: no space left")

    original = scheduling.copy_database
    monkeypatch.setattr(scheduling, "copy_database", full_disk)
    with pytest.raises(BusinessError):
        service.run_due()
    status = service.status()
    assert status["files"] == previous
    assert "secret" not in status["last_error"]
    assert status["last_success_at"] == datetime(2026, 10, 20, 4, tzinfo=UTC).isoformat()
    assert service.run_due() is None
    monkeypatch.setattr(scheduling, "copy_database", original)
    service.create()
    assert service.status()["last_error"] is None


def test_disabled_schedule_manual_backup_and_download_boundaries(populated, tmp_path):
    service = manager(populated, tmp_path / "backups", [datetime.now(UTC)], enabled=False)
    assert service.run_due() is None and service.status()["next_backup_at"] is None
    created = service.create()
    assert service.download_path(created["name"]).is_file()
    for invalid in ("app.db", "../app.db", "/etc/passwd", "lootsplit-daily-9999-99-99.db"):
        with pytest.raises(BusinessError, match="introuvable"):
            service.download_path(invalid)
    with service.lock:
        with pytest.raises(BusinessError, match="en cours"):
            service.create()


def test_missing_daily_copy_is_recreated_and_corrupt_state_does_not_stop_backups(
    populated, tmp_path
):
    clock = [datetime.now(UTC)]
    service = manager(populated, tmp_path / "backups", clock)
    result = service.run_due()
    service.download_path(result["name"]).unlink()
    assert service.run_due() is not None
    state = tmp_path / "backups" / "backup-state.json"
    state.write_text("not json")
    restarted = manager(populated, tmp_path / "backups", clock)
    assert restarted.run_due() is not None
    state.write_text(
        json.dumps({"last_success_at": "invalid-date", "last_error": "secret-server-path"})
    )
    restarted = manager(populated, tmp_path / "backups", clock)
    assert restarted.status()["last_success_at"] is None
    assert "secret" not in restarted.status()["last_error"]
    assert restarted.run_due() is not None


@pytest.mark.parametrize("hour", ["24:00", "3:00", "10:75", "invalid"])
def test_invalid_schedule_is_rejected(hour):
    with pytest.raises(ValueError):
        BackupConfiguration(time=hour)


def test_invalid_foreign_keys_reject_snapshot_before_publication(populated, tmp_path):
    damaged = backup(populated, tmp_path / "damaged")
    with closing(sqlite3.connect(damaged)) as db:
        db.execute("DELETE FROM envelopes WHERE id=1")
        db.commit()
    target = tmp_path / "rejected" / "backup.db"
    with pytest.raises(ValueError, match="références"):
        copy_database(damaged, target)
    assert not target.exists()
