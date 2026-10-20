import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event

from lootsplit.backup import backup
from lootsplit.models import BankConnection, Base


def create_database(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size:
        with sqlite3.connect(path) as previous:
            version = previous.execute("PRAGMA user_version").fetchone()[0]
            existing = previous.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'"
            ).fetchone()
        if version < 2 and existing:
            backup(path, path.parent / "backups" / "before-migration")
    engine = create_engine(
        f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        connection.execute("PRAGMA journal_mode=WAL")

    @event.listens_for(engine, "begin")
    def begin(connection):
        # Sérialise les lectures suivies d'écritures (réaffectations et imports).
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    with engine.begin() as connection:
        version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
        if version > 2:
            raise RuntimeError("Cette base nécessite une version plus récente de LootSplit.")
        if version == 0:
            # Adoption du premier schéma, qui ne portait pas encore de numéro de version.
            tables = [t for t in Base.metadata.sorted_tables if t.name != "bank_connection"]
            Base.metadata.create_all(connection, tables=tables)
            connection.exec_driver_sql("PRAGMA user_version=1")
        if version < 2:
            BankConnection.__table__.create(connection, checkfirst=True)
            connection.exec_driver_sql("PRAGMA user_version=2")
        # Défense supplémentaire contre une modification accidentelle du journal bancaire.
        for operation in ("UPDATE", "DELETE"):
            connection.exec_driver_sql(f"""
                CREATE TRIGGER IF NOT EXISTS immutable_transaction_{operation.lower()}
                BEFORE {operation} ON bank_transactions
                BEGIN SELECT RAISE(ABORT, 'Bank transactions are immutable'); END
            """)
        for table in ("ledger", "audit_log"):
            for operation in ("UPDATE", "DELETE"):
                connection.exec_driver_sql(f"""
                    CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()}
                    BEFORE {operation} ON {table}
                    BEGIN SELECT RAISE(ABORT, 'Append-only journal'); END
                """)
    return engine
