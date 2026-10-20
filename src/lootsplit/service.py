"""Cas d'usage transactionnels ; l'appelant contrôle commit et rollback."""

import json
from collections import Counter
from datetime import date
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lootsplit.domain import (
    BankTransaction,
    BusinessError,
    annual_chart,
    match_code,
    normalize_label,
    validate_cents,
    validate_code,
)
from lootsplit.models import (
    Account,
    Allocation,
    AuditLog,
    BankConnection,
    Envelope,
    ExternalIdentity,
    LedgerEntry,
    Transaction,
    now,
)


class LedgerService:
    def __init__(self, session: Session, actor: str = "ADMIN", today: date | None = None):
        self.db = session
        self.actor = actor
        self.today = today or date.today()

    def audit(self, event: str, entity: str, entity_id, old=None, new=None):
        self.db.add(
            AuditLog(
                event_type=event,
                entity_type=entity,
                entity_id=str(entity_id),
                old_value=json.dumps(old, ensure_ascii=False, default=str),
                new_value=json.dumps(new, ensure_ascii=False, default=str),
                actor=self.actor,
            )
        )

    def account(self) -> Account:
        account = self.db.get(Account, 1)
        if account is None:
            raise BusinessError("Initialisez d'abord le Livret A.")
        return account

    def envelope(self, envelope_id: int, active=False) -> Envelope:
        envelope = self.db.get(Envelope, envelope_id)
        if envelope is None:
            raise BusinessError("Enveloppe introuvable.")
        if active and envelope.status != "ACTIVE":
            raise BusinessError("Cette enveloppe est archivée.")
        return envelope

    def system_envelope(self) -> Envelope:
        return self.db.scalars(select(Envelope).where(Envelope.is_system.is_(True))).one()

    def create_envelope(self, name: str, code: str, **fields) -> Envelope:
        code = validate_code(code)
        if self.db.scalar(select(Envelope.id).where(Envelope.code == code)) is not None:
            raise BusinessError("Ce code est déjà utilisé, y compris dans les archives.")
        if not name.strip():
            raise BusinessError("Le nom ne peut pas être vide.")
        envelope = Envelope(name=name.strip(), code=code, **fields)
        self.db.add(envelope)
        self.db.flush()
        self.audit("CREATE", "envelope", envelope.id, new={"name": name, "code": code})
        return envelope

    def edit_envelope(self, envelope_id: int, changes: dict) -> Envelope:
        envelope = self.envelope(envelope_id, active=True)
        if envelope.is_system:
            raise BusinessError("L'enveloppe NON AFFECTÉ est protégée.")
        if changes.get("code") is not None:
            changes["code"] = validate_code(changes["code"])
            other = self.db.scalar(
                select(Envelope.id).where(
                    Envelope.code == changes["code"], Envelope.id != envelope_id
                )
            )
            if other is not None:
                raise BusinessError("Ce code est déjà utilisé.")
        if "name" in changes:
            changes["name"] = changes["name"].strip()
            if not changes["name"]:
                raise BusinessError("Le nom ne peut pas être vide.")
        old = {key: getattr(envelope, key) for key in changes}
        for key, value in changes.items():
            setattr(envelope, key, value)
        self.audit("EDIT", "envelope", envelope_id, old, changes)
        return envelope

    def initialize(self, name: str, start: date, balance_cents: int, allocations: dict[int, int]):
        validate_cents(balance_cents)
        for amount in allocations.values():
            validate_cents(amount)
        if self.db.get(Account, 1) is not None:
            raise BusinessError("Le compte a déjà été initialisé.")
        if start > self.today:
            raise BusinessError("La date de démarrage ne peut pas être future.")
        if balance_cents < 0 or any(amount < 0 for amount in allocations.values()):
            raise BusinessError("La répartition initiale doit être positive ou nulle.")
        if sum(allocations.values()) > balance_cents:
            raise BusinessError("La répartition dépasse le solde bancaire.")
        for envelope_id in allocations:
            self.envelope(envelope_id, active=True)
        self.db.add(
            Account(
                id=1,
                name=name,
                activation_date=start,
                opening_balance_cents=balance_cents,
                current_balance_cents=balance_cents,
            )
        )
        system = Envelope(name="NON AFFECTÉ", code=None, is_system=True, sort_order=2**30)
        self.db.add(system)
        self.db.flush()
        amounts = {**allocations, system.id: balance_cents - sum(allocations.values())}
        event_id = str(uuid4())
        for envelope_id, amount in amounts.items():
            self.db.add(
                LedgerEntry(
                    envelope_id=envelope_id,
                    amount_cents=amount,
                    effective_date=start,
                    kind="INITIAL",
                    event_id=event_id,
                    reason="Répartition initiale",
                )
            )
        self.audit(
            "INITIALIZE",
            "account",
            1,
            new={
                "date": start,
                "balance_cents": balance_cents,
                "allocations": amounts,
            },
        )
        self.db.flush()

    def balances(self) -> dict[int, int]:
        return dict(
            self.db.execute(
                select(LedgerEntry.envelope_id, func.sum(LedgerEntry.amount_cents)).group_by(
                    LedgerEntry.envelope_id
                )
            ).all()
        )

    def archive(self, envelope_id: int):
        envelope = self.envelope(envelope_id, active=True)
        if envelope.is_system:
            raise BusinessError("L'enveloppe NON AFFECTÉ est protégée.")
        if self.balances().get(envelope_id, 0) != 0:
            raise BusinessError("Réaffectez le solde avant d'archiver cette enveloppe.")
        envelope.status = "ARCHIVED"
        envelope.archived_at = now()
        self.audit("ARCHIVE", "envelope", envelope_id, "ACTIVE", "ARCHIVED")

    def import_transactions(
        self, transactions: list[BankTransaction], source: str, balance_cents: int
    ) -> dict[str, int]:
        validate_cents(balance_cents)
        account = self.account()
        system = self.system_envelope()
        codes = {
            e.code: e.id
            for e in self.db.scalars(
                select(Envelope).where(Envelope.status == "ACTIVE", Envelope.code.is_not(None))
            )
        }
        eligible = [t for t in transactions if t.booking_date > account.activation_date]
        if any(t.booking_date > self.today for t in eligible):
            raise BusinessError("Seules les opérations comptabilisées à ce jour sont acceptées.")
        # Deux lignes identiques sans identifiant pourraient être deux opérations légitimes.
        counts = Counter(t.fingerprint(1) for t in eligible)
        if any(counts[t.fingerprint(1)] > 1 and not t.provider_transaction_id for t in eligible):
            raise BusinessError("Lignes identiques sans identifiant : import ambigu à vérifier.")
        result = {"imported": 0, "duplicates": 0, "before_start": len(transactions) - len(eligible)}
        for item in eligible:
            fingerprint = item.fingerprint(1)
            identity = None
            if item.provider_transaction_id:
                identity = self.db.scalar(
                    select(ExternalIdentity).where(
                        ExternalIdentity.account_id == 1,
                        ExternalIdentity.source == source,
                        ExternalIdentity.provider_id == item.provider_transaction_id,
                    )
                )
            if identity:
                original = self.db.get(Transaction, identity.transaction_id)
                if original.fingerprint != fingerprint:
                    raise BusinessError(
                        "Une opération connue a changé chez le fournisseur. Import annulé."
                    )
                result["duplicates"] += 1
                continue
            candidates = list(
                self.db.scalars(select(Transaction).where(Transaction.fingerprint == fingerprint))
            )
            # Des identifiants distincts du même fournisseur restent des opérations distinctes.
            matches = [
                t
                for t in candidates
                if not (
                    item.provider_transaction_id
                    and self.db.scalar(
                        select(ExternalIdentity.id).where(
                            ExternalIdentity.transaction_id == t.id,
                            ExternalIdentity.source == source,
                        )
                    )
                )
            ]
            if len(matches) > 1:
                raise BusinessError("Plusieurs opérations identiques : rapprochement ambigu.")
            if matches:
                transaction = matches[0]
                result["duplicates"] += 1
            else:
                transaction = Transaction(
                    bank_account_id=1,
                    booking_date=item.booking_date,
                    value_date=item.value_date,
                    amount_cents=item.amount_cents,
                    raw_label=item.raw_label,
                    normalized_label=normalize_label(item.raw_label),
                    source=source,
                    fingerprint=fingerprint,
                    currency=item.currency,
                )
                self.db.add(transaction)
                self.db.flush()
                matched = match_code(item.raw_label, codes)
                target = matched if matched is not None else system.id
                self.db.add(
                    Allocation(
                        transaction_id=transaction.id,
                        envelope_id=target,
                        allocation_type="AUTO" if matched is not None else "SYSTEM",
                    )
                )
                self.db.add(
                    LedgerEntry(
                        envelope_id=target,
                        transaction_id=transaction.id,
                        event_id=str(uuid4()),
                        effective_date=item.booking_date,
                        amount_cents=item.amount_cents,
                        kind="BANK",
                        reason=item.raw_label,
                    )
                )
                result["imported"] += 1
            if item.provider_transaction_id:
                self.db.add(
                    ExternalIdentity(
                        account_id=1,
                        transaction_id=transaction.id,
                        source=source,
                        provider_id=item.provider_transaction_id,
                    )
                )
            self.db.flush()
        account.current_balance_cents = balance_cents
        account.last_sync_at = now()
        account.last_sync_error = None
        self.audit("IMPORT", "account", 1, new={**result, "source": source})
        self.db.flush()
        return result

    def correct_allocation(self, transaction_id: int, target_id: int):
        self.account()
        self.envelope(target_id, active=True)
        transaction = self.db.get(Transaction, transaction_id)
        allocation = self.db.get(Allocation, transaction_id)
        if transaction is None or allocation is None:
            raise BusinessError("Transaction introuvable.")
        if allocation.envelope_id == target_id:
            return
        old_id = allocation.envelope_id
        event_id = str(uuid4())
        # Les corrections sont visibles à leur date d'action, sans réécrire le passé.
        for envelope_id, sign in ((old_id, -1), (target_id, 1)):
            self.db.add(
                LedgerEntry(
                    envelope_id=envelope_id,
                    transaction_id=transaction_id,
                    event_id=event_id,
                    effective_date=self.today,
                    amount_cents=sign * transaction.amount_cents,
                    kind="CORRECTION",
                    reason="Correction manuelle d'affectation",
                )
            )
        allocation.envelope_id = target_id
        allocation.allocation_type = "MANUAL"
        self.audit("CORRECT_ALLOCATION", "transaction", transaction_id, old_id, target_id)
        self.db.flush()

    def reallocate(self, source_id: int, target_id: int, amount_cents: int, reason: str = ""):
        validate_cents(amount_cents)
        self.account()
        self.envelope(source_id, active=True)
        self.envelope(target_id, active=True)
        if source_id == target_id or amount_cents <= 0:
            raise BusinessError("Choisissez deux enveloppes distinctes et un montant positif.")
        if amount_cents > self.balances().get(source_id, 0):
            raise BusinessError("Le montant dépasse le solde disponible dans l'enveloppe source.")
        event_id = str(uuid4())
        for envelope_id, sign in ((source_id, -1), (target_id, 1)):
            self.db.add(
                LedgerEntry(
                    envelope_id=envelope_id,
                    event_id=event_id,
                    effective_date=self.today,
                    amount_cents=sign * amount_cents,
                    kind="REALLOCATION",
                    reason=reason,
                )
            )
        self.audit(
            "REALLOCATE",
            "reallocation",
            event_id,
            new={
                "from": source_id,
                "to": target_id,
                "amount_cents": amount_cents,
                "reason": reason,
            },
        )
        self.db.flush()
        return event_id

    def reconciliation(self):
        account = self.account()
        total = sum(self.balances().values())
        difference = account.current_balance_cents - total
        connection = self.db.get(BankConnection, 1)
        bank_error = (
            "La dernière synchronisation bancaire a échoué. Consultez les paramètres de connexion."
            if connection and connection.error_code
            else None
        )
        return {
            "bank_balance_cents": account.current_balance_cents,
            "envelopes_total_cents": total,
            "unassigned_cents": self.balances().get(self.system_envelope().id, 0),
            "difference_cents": difference,
            "reconciled": difference == 0,
            "last_sync_at": account.last_sync_at,
            "last_sync_error": account.last_sync_error or bank_error,
        }

    def anomalies(self):
        reconciliation = self.reconciliation()
        unassigned = list(
            self.db.scalars(
                select(Allocation.transaction_id).where(
                    Allocation.envelope_id == self.system_envelope().id
                )
            )
        )
        negative = [envelope_id for envelope_id, amount in self.balances().items() if amount < 0]
        suspicious = list(
            self.db.scalars(
                select(Transaction.fingerprint)
                .group_by(Transaction.fingerprint)
                .having(func.count() > 1)
            )
        )
        count = (
            len(unassigned)
            + len(negative)
            + len(suspicious)
            + int(not reconciliation["reconciled"])
            + int(bool(reconciliation["last_sync_error"]))
        )
        return {
            "count": count,
            "unassigned_transaction_ids": unassigned,
            "negative_envelope_ids": negative,
            "suspected_duplicate_fingerprints": suspicious,
            "reconciliation": reconciliation,
        }

    def chart(self, envelope_id: int, year: int):
        self.envelope(envelope_id)
        account = self.account()
        entries = self.db.execute(
            select(LedgerEntry.effective_date, LedgerEntry.amount_cents).where(
                LedgerEntry.envelope_id == envelope_id
            )
        ).all()
        # Aucune courbe inventée avant la date de démarrage.
        return [
            p
            for p in annual_chart(entries, year, self.today)
            if p["date"] >= account.activation_date.isoformat()
        ]
