"""Sauvegarde SQLite cohérente, y compris lorsque WAL est actif."""

import argparse
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


def copy_database(source: Path, target: Path, *, application=False) -> Path:
    """Copie publiée seulement après fermeture et validation, sans fichiers WAL annexes."""
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == target.resolve():
        raise ValueError("La sauvegarde doit être distincte de la base source.")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".lootsplit-", suffix=".partial", dir=target.parent
    )
    os.close(descriptor)
    staging = Path(temporary)
    deadline = time.monotonic() + 120

    def progress(*_):
        if time.monotonic() > deadline:
            raise TimeoutError("Le délai de sauvegarde SQLite a été dépassé.")

    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(staging)) as copy:
                original.backup(copy, pages=256, progress=progress, sleep=0.05)
                copy.execute("PRAGMA journal_mode=DELETE")
                if copy.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("Sauvegarde SQLite invalide.")
                if copy.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ValueError("La sauvegarde contient des références incohérentes.")
                if application:
                    validate_application(copy)
        with staging.open("rb+") as complete:
            os.fsync(complete.fileno())
        staging.replace(target)
        return target
    finally:
        staging.unlink(missing_ok=True)
        for suffix in ("-journal", "-wal", "-shm"):
            Path(str(staging) + suffix).unlink(missing_ok=True)


def validate_application(connection):
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1, 2):
        raise ValueError("Cette sauvegarde nécessite une version différente de LootSplit.")
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    required = {"accounts", "envelopes", "bank_transactions", "allocations", "ledger", "audit_log"}
    if not required.issubset(tables) or (version == 2 and "bank_connection" not in tables):
        raise ValueError("Le fichier n'est pas une sauvegarde complète de LootSplit.")


def backup(source: Path, destination: Path) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"lootsplit-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.db"
    return copy_database(source, target)


def restore(source: Path, destination: Path) -> Path:
    """Restauration hors ligne dans un dossier neuf ; aucune base existante remplacée."""
    destination.mkdir()  # Refuse même un dossier existant vide ou un lien symbolique.
    try:
        return copy_database(source, destination / "app.db", application=True)
    except Exception:
        # Uniquement le dossier neuf créé par cet appel, et seulement s'il est vide.
        try:
            destination.rmdir()
        except OSError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path, default=Path(os.getenv("LOOTSPLIT_DB_PATH", "/data/app.db"))
    )
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--restore", type=Path, metavar="SAUVEGARDE")
    args = parser.parse_args()
    if args.restore:
        if args.destination is None:
            parser.error("--restore exige --destination avec un nouveau dossier.")
        print(restore(args.restore, args.destination))
    else:
        print(
            backup(
                args.source,
                args.destination or Path(os.getenv("LOOTSPLIT_BACKUP_PATH", "/data/backups")),
            )
        )


if __name__ == "__main__":
    main()
