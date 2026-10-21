import csv
import io
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from lootsplit.auth import Sessions, session_from_request
from lootsplit.auth import router as auth_router
from lootsplit.backups import Backups
from lootsplit.banking import Banking
from lootsplit.connectors import CsvConnector
from lootsplit.database import create_database
from lootsplit.domain import MAX_CENTS, BusinessError
from lootsplit.models import (
    Account,
    Allocation,
    AuditLog,
    BankConnection,
    Envelope,
    ExternalIdentity,
    LedgerEntry,
    Transaction,
)
from lootsplit.service import LedgerService

Cents = Annotated[StrictInt, Field(ge=-MAX_CENTS, le=MAX_CENTS)]
PositiveCents = Annotated[StrictInt, Field(gt=0, le=MAX_CENTS)]
Name = Annotated[str, Field(min_length=1, max_length=100)]
Code = Annotated[str, Field(min_length=1, max_length=20)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnvelopeCreate(Input):
    name: Name
    code: Code
    description: str = Field(default="", max_length=1000)
    icon: str = Field(default="", max_length=40)
    sort_order: StrictInt = Field(default=0, ge=0, le=100_000)


class EnvelopeUpdate(Input):
    name: Name | None = None
    code: Code | None = None
    description: str | None = Field(default=None, max_length=1000)
    icon: str | None = Field(default=None, max_length=40)
    sort_order: StrictInt | None = Field(default=None, ge=0, le=100_000)

    @model_validator(mode="after")
    def non_null(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Les champs renseignés ne peuvent pas être null.")
        return self


class Setup(Input):
    name: Name = "Compte de réserve"
    activation_date: date
    opening_balance_cents: Annotated[StrictInt, Field(ge=0, le=MAX_CENTS)]
    allocations: dict[int, Annotated[StrictInt, Field(ge=0, le=MAX_CENTS)]]


class CsvImport(Input):
    content: str = Field(max_length=2_000_000)
    bank_balance_cents: Cents


class Correction(Input):
    envelope_id: StrictInt = Field(gt=0)


class Reallocation(Input):
    from_envelope_id: StrictInt = Field(gt=0)
    to_envelope_id: StrictInt = Field(gt=0)
    amount_cents: PositiveCents
    reason: str = Field(default="", max_length=1000)


class BankSelection(Input):
    choice_id: str = Field(min_length=1, max_length=100)
    confirmed: bool = Field(strict=True)


class BankSchedule(Input):
    enabled: bool = Field(strict=True)
    interval_hours: StrictInt = Field(ge=1, le=168)


def serialize(row) -> dict:
    return {column.key: getattr(row, column.key) for column in inspect(type(row)).columns}


def create_app(database_path: Path | None = None, admin_token: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        token = admin_token if admin_token is not None else os.getenv("LOOTSPLIT_ADMIN_TOKEN", "")
        if len(token) < 32:
            raise RuntimeError("LOOTSPLIT_ADMIN_TOKEN doit contenir au moins 32 caractères.")
        app.state.admin_token = token
        app.state.sessions = Sessions()
        app.state.secure_cookie = os.getenv("LOOTSPLIT_SECURE_COOKIE", "false").lower() == "true"
        path = database_path or Path(os.getenv("LOOTSPLIT_DB_PATH", "data/app.db"))
        app.state.engine = create_database(path)
        app.state.backups = Backups(
            path,
            Path(os.environ["LOOTSPLIT_BACKUP_PATH"])
            if os.getenv("LOOTSPLIT_BACKUP_PATH")
            else None,
        )
        app.state.banking = Banking(app.state.engine)
        app.state.banking.start()
        app.state.backups.start()
        try:
            yield
        finally:
            app.state.backups.close()
            app.state.banking.close()
            app.state.engine.dispose()

    app = FastAPI(
        title="LootSplit — Réserves",
        version="0.1.0",
        lifespan=lifespan,
        description="Socle métier. Montants en centimes entiers. Aucune opération bancaire.",
    )
    bearer = HTTPBearer(auto_error=False)
    app.include_router(auth_router)

    def authenticate(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if credentials is not None:
            if secrets.compare_digest(
                credentials.credentials.encode(), app.state.admin_token.encode()
            ):
                return "ADMIN"
            raise HTTPException(
                401, "Authentification requise.", headers={"WWW-Authenticate": "Bearer"}
            )
        session_from_request(request, write=request.method not in {"GET", "HEAD", "OPTIONS"})
        return "ADMIN"

    def service(actor: Annotated[str, Depends(authenticate)]):
        with Session(app.state.engine) as session, session.begin():
            yield LedgerService(session, actor)

    Service = Annotated[LedgerService, Depends(service)]
    Actor = Annotated[str, Depends(authenticate)]

    @app.get("/api/backups")
    def backups_status(actor: Actor):
        return app.state.backups.status()

    @app.post("/api/backups", status_code=201)
    def create_backup(actor: Actor):
        return app.state.backups.create()

    @app.get("/api/backups/{name}/download")
    def download_backup(name: str, actor: Actor):
        path = app.state.backups.download_path(name)
        return FileResponse(path, filename=path.name, media_type="application/vnd.sqlite3")

    @app.get("/api/banking/status")
    def banking_status(actor: Actor):
        return app.state.banking.status()

    @app.post("/api/banking/accounts")
    def discover_accounts(actor: Actor):
        return app.state.banking.discover()

    @app.post("/api/banking/selection")
    def select_bank_account(body: BankSelection, actor: Actor):
        return app.state.banking.select(body.choice_id, body.confirmed, actor)

    @app.patch("/api/banking/schedule")
    def schedule_bank_sync(body: BankSchedule, actor: Actor):
        return app.state.banking.configure_schedule(body.enabled, body.interval_hours, actor)

    @app.post("/api/sync")
    def sync_bank(actor: Actor):
        return app.state.banking.sync()

    @app.exception_handler(BusinessError)
    async def business_error(_, exc: BusinessError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health", include_in_schema=False)
    def health():
        with app.state.engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return {"status": "ok"}

    @app.post("/api/setup", status_code=201)
    def setup(body: Setup, svc: Service):
        svc.initialize(
            body.name, body.activation_date, body.opening_balance_cents, body.allocations
        )
        return svc.reconciliation()

    @app.get("/api/accounts")
    def accounts(svc: Service):
        return [serialize(account) for account in svc.db.scalars(select(Account))]

    @app.get("/api/envelopes")
    def envelopes(svc: Service, include_archived: bool = False):
        query = select(Envelope).order_by(Envelope.sort_order, Envelope.id)
        if not include_archived:
            query = query.where(Envelope.status == "ACTIVE")
        balances = svc.balances()
        return [
            {**serialize(e), "balance_cents": balances.get(e.id, 0)} for e in svc.db.scalars(query)
        ]

    @app.post("/api/envelopes", status_code=201)
    def create_envelope(body: EnvelopeCreate, svc: Service):
        return serialize(svc.create_envelope(**body.model_dump()))

    @app.patch("/api/envelopes/{envelope_id}")
    def edit_envelope(envelope_id: int, body: EnvelopeUpdate, svc: Service):
        return serialize(svc.edit_envelope(envelope_id, body.model_dump(exclude_unset=True)))

    @app.post("/api/envelopes/{envelope_id}/archive")
    def archive(envelope_id: int, svc: Service):
        svc.archive(envelope_id)
        return {"status": "ARCHIVED"}

    @app.get("/api/reconciliation")
    def reconciliation(svc: Service):
        return svc.reconciliation()

    @app.get("/api/anomalies")
    def anomalies(svc: Service):
        return svc.anomalies()

    @app.get("/api/dashboard")
    def dashboard(svc: Service):
        reconciliation = svc.reconciliation()
        month_start = svc.today.replace(day=1)
        cards = []
        balances = svc.balances()
        for envelope in svc.db.scalars(
            select(Envelope)
            .where(Envelope.status == "ACTIVE")
            .order_by(Envelope.sort_order, Envelope.id)
        ):
            entries = list(
                svc.db.scalars(
                    select(LedgerEntry).where(
                        LedgerEntry.envelope_id == envelope.id, LedgerEntry.kind != "INITIAL"
                    )
                )
            )
            current_month = [e for e in entries if month_start <= e.effective_date <= svc.today]
            cards.append(
                {
                    **serialize(envelope),
                    "balance_cents": balances.get(envelope.id, 0),
                    "month_net_cents": sum(e.amount_cents for e in current_month),
                    "month_movement_count": len(current_month),
                    "month_message": None if current_month else "Aucun mouvement ce mois-ci",
                    "last_movement_date": max((e.effective_date for e in entries), default=None),
                    "chart": svc.chart(envelope.id, svc.today.year),
                }
            )
        return {"reconciliation": reconciliation, "envelopes": cards, "anomalies": svc.anomalies()}

    @app.post("/api/import/csv")
    def import_csv(body: CsvImport, svc: Service):
        connector = CsvConnector(body.content, body.bank_balance_cents)
        # Le pipeline comptabilise explicitement les lignes avant la date d'ouverture.
        result = svc.import_transactions(
            connector.transactions, connector.source, connector.get_balance("1")
        )
        return {**result, "reconciliation": svc.reconciliation()}

    @app.get("/api/transactions/unassigned")
    def unassigned(svc: Service):
        return [
            serialize(t)
            for t in svc.db.scalars(
                select(Transaction)
                .join(Allocation)
                .where(Allocation.envelope_id == svc.system_envelope().id)
                .order_by(Transaction.booking_date.desc(), Transaction.id.desc())
            )
        ]

    @app.get("/api/transactions")
    def transactions(
        svc: Service,
        envelope_id: int | None = None,
        since: date | None = None,
        until: date | None = None,
        text: Annotated[str, Query(max_length=200)] = "",
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        query = (
            select(Transaction, Allocation, Envelope.name)
            .select_from(Transaction)
            .join(Allocation, Allocation.transaction_id == Transaction.id)
            .join(Envelope, Envelope.id == Allocation.envelope_id)
        )
        if envelope_id is not None:
            query = query.where(Allocation.envelope_id == envelope_id)
        if since:
            query = query.where(Transaction.booking_date >= since)
        if until:
            query = query.where(Transaction.booking_date <= until)
        if text:
            query = query.where(Transaction.raw_label.contains(text, autoescape=True))
        query = query.order_by(Transaction.booking_date.desc(), Transaction.id.desc())
        return [
            {**serialize(t), "allocation": serialize(a), "envelope_name": name}
            for t, a, name in svc.db.execute(query.offset(offset).limit(limit))
        ]

    @app.patch("/api/transactions/{transaction_id}/allocation")
    def correct_allocation(transaction_id: int, body: Correction, svc: Service):
        svc.correct_allocation(transaction_id, body.envelope_id)
        return {"status": "ok"}

    @app.post("/api/reallocations", status_code=201)
    def reallocate(body: Reallocation, svc: Service):
        return {
            "event_id": svc.reallocate(
                body.from_envelope_id, body.to_envelope_id, body.amount_cents, body.reason
            )
        }

    @app.get("/api/envelopes/{envelope_id}/history")
    def history(
        envelope_id: int,
        svc: Service,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        svc.envelope(envelope_id)
        return [
            serialize(e)
            for e in svc.db.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.envelope_id == envelope_id)
                .order_by(LedgerEntry.effective_date.desc(), LedgerEntry.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ]

    @app.get("/api/envelopes/{envelope_id}/chart")
    def chart(envelope_id: int, svc: Service, year: Annotated[int, Query(ge=1900, le=9999)]):
        return svc.chart(envelope_id, year)

    @app.get("/api/envelopes/{envelope_id}/summary")
    def envelope_summary(
        envelope_id: int, svc: Service, year: Annotated[int, Query(ge=1900, le=9998)]
    ):
        envelope = svc.envelope(envelope_id)
        rows = (
            svc.db.execute(
                select(LedgerEntry.amount_cents).where(
                    LedgerEntry.envelope_id == envelope_id,
                    LedgerEntry.kind != "INITIAL",
                    LedgerEntry.effective_date >= date(year, 1, 1),
                    LedgerEntry.effective_date < date(year + 1, 1, 1),
                )
            )
            .scalars()
            .all()
        )
        return {
            **serialize(envelope),
            "balance_cents": svc.balances().get(envelope_id, 0),
            "year": year,
            "in_cents": sum(v for v in rows if v > 0),
            "out_cents": sum(v for v in rows if v < 0),
        }

    @app.get("/api/movements")
    def movements(
        svc: Service,
        envelope_id: int | None = None,
        since: date | None = None,
        until: date | None = None,
        kind: Annotated[str, Query(pattern="^(INITIAL|BANK|REALLOCATION|CORRECTION)$")]
        | None = None,
        min_cents: Annotated[int | None, Query(ge=-MAX_CENTS, le=MAX_CENTS)] = None,
        max_cents: Annotated[int | None, Query(ge=-MAX_CENTS, le=MAX_CENTS)] = None,
        text: Annotated[str, Query(max_length=200)] = "",
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        query = select(LedgerEntry, Envelope.name).join(Envelope)
        if envelope_id is not None:
            query = query.where(LedgerEntry.envelope_id == envelope_id)
        if since is not None:
            query = query.where(LedgerEntry.effective_date >= since)
        if until is not None:
            query = query.where(LedgerEntry.effective_date <= until)
        if kind is not None:
            query = query.where(LedgerEntry.kind == kind)
        if min_cents is not None:
            query = query.where(LedgerEntry.amount_cents >= min_cents)
        if max_cents is not None:
            query = query.where(LedgerEntry.amount_cents <= max_cents)
        if text:
            query = query.where(LedgerEntry.reason.contains(text, autoescape=True))
        total = svc.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = svc.db.execute(
            query.order_by(LedgerEntry.effective_date.desc(), LedgerEntry.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return {
            "total": total,
            "items": [{**serialize(entry), "envelope_name": name} for entry, name in rows],
        }

    @app.get("/api/audit")
    def audit(
        svc: Service,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return [
            serialize(a)
            for a in svc.db.scalars(
                select(AuditLog).order_by(AuditLog.id.desc()).offset(offset).limit(limit)
            )
        ]

    @app.get("/api/export/json")
    def export_json(svc: Service):
        tables = {
            "accounts": Account,
            "envelopes": Envelope,
            "transactions": Transaction,
            "external_identities": ExternalIdentity,
            "allocations": Allocation,
            "ledger": LedgerEntry,
            "audit": AuditLog,
            "bank_connection": BankConnection,
        }
        payload = {
            "schema_version": 2,
            **{
                key: [serialize(row) for row in svc.db.scalars(select(model))]
                for key, model in tables.items()
            },
        }
        return JSONResponse(
            jsonable_encoder(payload),
            headers={"Content-Disposition": 'attachment; filename="lootsplit.json"'},
        )

    @app.get("/api/export/csv")
    def export_csv(svc: Service):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["date", "envelope_id", "amount_cents", "type", "label", "event_id"])
        for entry in svc.db.scalars(
            select(LedgerEntry).order_by(LedgerEntry.effective_date, LedgerEntry.id)
        ):
            # Les tableurs ne doivent pas interpréter les libellés comme des formules.
            reason = entry.reason
            if reason.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
                reason = "'" + reason
            writer.writerow(
                [
                    entry.effective_date,
                    entry.envelope_id,
                    entry.amount_cents,
                    entry.kind,
                    reason,
                    entry.event_id,
                ]
            )
        return Response(
            "\ufeff" + stream.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="lootsplit-mouvements.csv"'},
        )

    frontend = Path(os.getenv("LOOTSPLIT_FRONTEND_PATH", "frontend/dist"))
    if (frontend / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def frontend_index():
            return FileResponse(frontend / "index.html")

    return app


app = create_app()
