from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("id = 1"),)
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    name: Mapped[str]
    activation_date: Mapped[date]
    opening_balance_cents: Mapped[int]
    current_balance_cents: Mapped[int]
    last_sync_at: Mapped[datetime | None]
    last_sync_error: Mapped[str | None]


class Envelope(Base):
    __tablename__ = "envelopes"
    __table_args__ = (CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    code: Mapped[str | None] = mapped_column(String(20), unique=True)
    description: Mapped[str] = mapped_column(default="")
    icon: Mapped[str] = mapped_column(default="")
    sort_order: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="ACTIVE")
    is_system: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=now)
    archived_at: Mapped[datetime | None]


class Transaction(Base):
    __tablename__ = "bank_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    booking_date: Mapped[date]
    value_date: Mapped[date | None]
    amount_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(default="EUR")
    raw_label: Mapped[str]
    normalized_label: Mapped[str]
    source: Mapped[str]
    imported_at: Mapped[datetime] = mapped_column(default=now)
    fingerprint: Mapped[str] = mapped_column(index=True)


class ExternalIdentity(Base):
    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("account_id", "source", "provider_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    transaction_id: Mapped[int] = mapped_column(ForeignKey("bank_transactions.id"))
    source: Mapped[str]
    provider_id: Mapped[str]


class Allocation(Base):
    __tablename__ = "allocations"
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("bank_transactions.id"), primary_key=True
    )
    envelope_id: Mapped[int] = mapped_column(ForeignKey("envelopes.id"))
    allocation_type: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=now)


class LedgerEntry(Base):
    __tablename__ = "ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    envelope_id: Mapped[int] = mapped_column(ForeignKey("envelopes.id"), index=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("bank_transactions.id"))
    event_id: Mapped[str] = mapped_column(index=True)
    effective_date: Mapped[date]
    amount_cents: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str]
    reason: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str]
    entity_type: Mapped[str]
    entity_id: Mapped[str]
    old_value: Mapped[str]
    new_value: Mapped[str]
    actor: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=now)


class BankConnection(Base):
    __tablename__ = "bank_connection"
    __table_args__ = (CheckConstraint("id = 1"),)
    id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), primary_key=True, default=1)
    provider_account_id: Mapped[str]
    masked_iban: Mapped[str]
    auto_sync_enabled: Mapped[bool] = mapped_column(default=False)
    interval_hours: Mapped[int] = mapped_column(default=6)
    next_sync_at: Mapped[datetime | None]
    last_attempt_at: Mapped[datetime | None]
    last_success_at: Mapped[datetime | None]
    error_code: Mapped[str | None]
