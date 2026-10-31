"""Correction sauvegardée du stock initial, sans modifier les opérations bancaires."""

import secrets
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lootsplit.account_change import change_preview
from lootsplit.domain import BusinessError, validate_cents
from lootsplit.models import LedgerEntry
from lootsplit.service import LedgerService


def opening_preview(service: LedgerService):
    snapshot = change_preview(service)
    amounts = dict(
        service.db.execute(
            select(LedgerEntry.envelope_id, func.sum(LedgerEntry.amount_cents))
            .where(LedgerEntry.kind == "INITIAL")
            .group_by(LedgerEntry.envelope_id)
        ).all()
    )
    return {
        **snapshot,
        "bank_balance_known": service.account().last_sync_at is not None,
        "envelopes": [
            {**envelope, "initial_cents": amounts.get(envelope["id"], 0)}
            for envelope in snapshot["envelopes"]
        ],
    }


def correct_opening(engine, banking, backups, revision, balance_cents, allocations, reason, actor):
    validate_cents(balance_cents)
    for amount in allocations.values():
        validate_cents(amount)
    if balance_cents < 0 or any(amount < 0 for amount in allocations.values()):
        raise BusinessError("La répartition initiale doit être positive ou nulle.")
    reason = reason.strip()
    if not reason:
        raise BusinessError("Indiquez le motif de la correction.")
    if not banking.lock.acquire(blocking=False):
        raise BusinessError(
            "Une connexion bancaire est en cours. Attendez sa fin avant de corriger."
        )
    try:
        with Session(engine) as session, session.begin():
            service = LedgerService(session, actor)
            snapshot = opening_preview(service)
            if not secrets.compare_digest(snapshot["revision"], revision):
                raise BusinessError(
                    "Les données ont changé. Rechargez le formulaire avant de confirmer à nouveau."
                )
            envelopes = {e["id"]: e for e in snapshot["envelopes"]}
            if any(i not in envelopes or envelopes[i]["is_system"] for i in allocations):
                raise BusinessError(
                    "Choisissez uniquement des enveloppes existantes hors NON AFFECTÉ."
                )
            # Le formulaire transmet la répartition complète, y compris les archives inchangées.
            targets = {i: allocations.get(i, 0) for i, e in envelopes.items() if not e["is_system"]}
            if any(
                e["status"] == "ARCHIVED" and targets[i] != e["initial_cents"]
                for i, e in envelopes.items()
                if not e["is_system"]
            ):
                raise BusinessError(
                    "La répartition initiale des enveloppes archivées est conservée."
                )
            if sum(targets.values()) > balance_cents:
                raise BusinessError("La répartition dépasse le solde initial corrigé.")
            targets[service.system_envelope().id] = balance_cents - sum(targets.values())
            deltas = {i: amount - envelopes[i]["initial_cents"] for i, amount in targets.items()}
            if not any(deltas.values()):
                raise BusinessError("Le solde et sa répartition sont inchangés.")
            # Même verrou transactionnel que le changement de compte : sauvegarde du dernier
            # état validé avant toute écriture. Les triggers d'immutabilité restent actifs.
            saved = backups.create()
            account = service.account()
            event_id = str(uuid4())
            for envelope_id, delta in deltas.items():
                if delta:
                    session.add(
                        LedgerEntry(
                            envelope_id=envelope_id,
                            amount_cents=delta,
                            effective_date=account.activation_date,
                            kind="INITIAL",
                            event_id=event_id,
                            reason=f"Correction du solde initial : {reason}",
                        )
                    )
            account.opening_balance_cents = balance_cents
            # Avant le premier relevé, le solde affiché n'est qu'une copie du stock initial.
            # Après un import, il appartient à la banque et doit rester inchangé.
            if not snapshot["bank_balance_known"]:
                account.current_balance_cents = balance_cents
            service.audit(
                "CORRECT_OPENING_BALANCE",
                "account",
                account.id,
                old={
                    "balance_cents": snapshot["opening_balance_cents"],
                    "allocations": {i: e["initial_cents"] for i, e in envelopes.items()},
                },
                new={
                    "balance_cents": balance_cents,
                    "allocations": targets,
                    "reason": reason,
                    "backup_name": saved["name"],
                },
            )
            session.flush()
            result = service.reconciliation()
        return {"backup": saved, "reconciliation": result}
    finally:
        banking.lock.release()
