"""Changement explicite de compte : sauvegarde, remise à zéro et nouvelle initialisation."""

import hashlib
import json
import secrets

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from lootsplit.database import IMMUTABLE_TRIGGERS, protect_history
from lootsplit.domain import BusinessError
from lootsplit.models import Account as ReserveAccount
from lootsplit.models import (
    Allocation,
    AuditLog,
    BankConnection,
    Envelope,
    ExternalIdentity,
    LedgerEntry,
    Transaction,
)
from lootsplit.service import LedgerService


def change_preview(service: LedgerService):
    account = service.account()
    connection = service.db.get(BankConnection, 1)
    balances = service.balances()
    last_audit = service.db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    snapshot = {
        "activation_date": account.activation_date.isoformat(),
        "opening_balance_cents": account.opening_balance_cents,
        "bank_balance_cents": account.current_balance_cents,
        "difference_cents": service.reconciliation()["difference_cents"],
        "masked_iban": connection.masked_iban if connection else None,
        "transaction_count": service.db.scalar(select(func.count()).select_from(Transaction)),
        "envelopes": [
            {
                "id": envelope.id,
                "name": envelope.name,
                "code": envelope.code,
                "status": envelope.status,
                "is_system": envelope.is_system,
                "balance_cents": balances.get(envelope.id, 0),
            }
            for envelope in service.db.scalars(
                select(Envelope).order_by(Envelope.sort_order, Envelope.id)
            )
        ],
    }
    # L'audit distingue aussi deux suivis successifs ayant les mêmes soldes et identifiants.
    state = {
        **snapshot,
        "last_audit": (
            [last_audit.id, str(last_audit.created_at), last_audit.new_value]
            if last_audit
            else None
        ),
    }
    revision = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    return {**snapshot, "revision": revision}


def change_account(engine, banking, backups, revision: str, actor: str):
    if not banking.lock.acquire(blocking=False):
        raise BusinessError(
            "Une connexion bancaire est en cours. Attendez sa fin avant de changer de compte."
        )
    try:
        # BEGIN IMMEDIATE bloque les écritures concurrentes jusqu'à la fin de la sauvegarde
        # et du changement. La copie SQLite utilise une connexion de lecture distincte.
        with Session(engine) as session, session.begin():
            service = LedgerService(session, actor)
            snapshot = change_preview(service)
            if not secrets.compare_digest(snapshot["revision"], revision):
                raise BusinessError(
                    "Les données ont changé. Rechargez le récapitulatif et recopiez les montants "
                    "avant de confirmer à nouveau."
                )
            saved = backups.create()
            connection = session.connection()
            # Exception volontaire et transactionnelle à l'immutabilité, réservée à cette
            # remise à zéro sauvegardée. En cas d'échec, les données et triggers sont restaurés.
            for name in IMMUTABLE_TRIGGERS:
                connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {name}")
            for model in (
                Allocation,
                ExternalIdentity,
                LedgerEntry,
                Transaction,
                BankConnection,
                ReserveAccount,
                AuditLog,
            ):
                session.execute(delete(model))
            session.execute(delete(Envelope).where(Envelope.is_system.is_(True)))
            protect_history(connection)
            service.audit(
                "CHANGE_RESERVE_ACCOUNT",
                "account",
                1,
                old=snapshot,
                new={"backup_name": saved["name"], "requires_setup": True},
            )
        banking.choices.clear()
        banking.discovery_error = None
        return {"requires_setup": True, "backup": saved}
    finally:
        banking.lock.release()
