"""Configuration publique, sélection du compte de réserve et synchronisation sérialisée."""

import secrets
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from lootsplit.domain import BusinessError
from lootsplit.models import BankConnection
from lootsplit.service import LedgerService
from lootsplit.sync import synchronize
from lootsplit.woob_connector import MESSAGES, BankConfiguration, ConnectorError, WoobConnector


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)


def timestamp(value):
    return value.isoformat() + "Z" if value else None


class Banking:
    def __init__(self, engine: Engine, configuration=None, factory=WoobConnector):
        self.engine = engine
        self.configuration = configuration or BankConfiguration.from_environment()
        self.factory = factory
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None
        self.choices = {}
        self.discovery_error = None

    def status(self):
        with Session(self.engine) as session:
            connection = session.get(BankConnection, 1)
            code = connection.error_code if connection else self.discovery_error
            config = self.configuration
            return {
                "credentials_configured": config.credentials_configured,
                "module_installed": config.module_installed,
                "configured": config.credentials_configured and config.module_installed,
                "connected": connection is not None,
                "masked_iban": connection.masked_iban if connection else None,
                "running": self.lock.locked(),
                "auto_sync_enabled": connection.auto_sync_enabled if connection else False,
                "interval_hours": connection.interval_hours if connection else 6,
                "last_attempt_at": timestamp(connection.last_attempt_at) if connection else None,
                "last_success_at": timestamp(connection.last_success_at) if connection else None,
                "next_sync_at": timestamp(connection.next_sync_at) if connection else None,
                "error_code": code,
                "error": MESSAGES.get(code),
                "automatic_paused": code in {"credentials", "action_required", "account"},
            }

    def discover(self):
        if not self.lock.acquire(blocking=False):
            raise BusinessError("Une connexion bancaire est déjà en cours.")
        try:
            items = self.factory(self.configuration).discover()
            choices = {}
            response = []
            for item in items:
                choice_id = secrets.token_urlsafe(24)
                choices[choice_id] = (time.monotonic() + 600, item)
                response.append(
                    {
                        "choice_id": choice_id,
                        "name": item["name"],
                        "balance_cents": item["balance_cents"],
                        "masked_iban": item["masked_iban"],
                    }
                )
            self.choices = choices
            self.discovery_error = None
            return response
        except ConnectorError as exc:
            self.discovery_error = exc.code
            raise
        except Exception:
            self.discovery_error = "unavailable"
            raise ConnectorError("unavailable") from None
        finally:
            self.lock.release()

    def select(self, choice_id: str, confirmed: bool, actor: str):
        if not confirmed:
            raise BusinessError(
                "Confirmez qu'il s'agit du compte de réserve déjà suivi dans l'application."
            )
        if not self.lock.acquire(blocking=False):
            raise BusinessError("Une connexion bancaire est déjà en cours.")
        try:
            choice = self.choices.get(choice_id)
            if not choice or choice[0] <= time.monotonic():
                raise BusinessError("La sélection a expiré. Rechargez la liste des comptes.")
            item = choice[1]
            with Session(self.engine) as session, session.begin():
                svc = LedgerService(session, actor)
                svc.account()
                connection = session.get(BankConnection, 1)
                if connection and connection.provider_account_id != item["id"]:
                    raise BusinessError(
                        "Un autre compte de réserve est déjà associé. Le changement de compte "
                        "nécessite une nouvelle initialisation sur une base distincte."
                    )
                if connection is None:
                    session.add(
                        BankConnection(
                            id=1,
                            provider_account_id=item["id"],
                            masked_iban=item["masked_iban"],
                        )
                    )
                svc.audit(
                    "CONNECT_BANK",
                    "account",
                    1,
                    new={"masked_iban": item["masked_iban"]},
                )
        finally:
            self.lock.release()
        return self.status()

    def configure_schedule(self, enabled: bool, interval_hours: int, actor: str):
        with Session(self.engine) as session, session.begin():
            connection = session.get(BankConnection, 1)
            if not connection:
                raise BusinessError("Sélectionnez d'abord le compte de réserve à synchroniser.")
            old = {
                "enabled": connection.auto_sync_enabled,
                "interval_hours": connection.interval_hours,
            }
            connection.auto_sync_enabled = enabled
            connection.interval_hours = interval_hours
            connection.next_sync_at = (
                utc_now() + timedelta(hours=interval_hours) if enabled else None
            )
            LedgerService(session, actor).audit(
                "BANK_SCHEDULE",
                "account",
                1,
                old,
                {
                    "enabled": enabled,
                    "interval_hours": interval_hours,
                },
            )
        return self.status()

    def sync(self, manual=True):
        if not self.lock.acquire(blocking=False):
            if not manual:
                return None
            raise BusinessError("Une connexion bancaire est déjà en cours.")
        try:
            with Session(self.engine) as session, session.begin():
                connection = session.get(BankConnection, 1)
                if not connection:
                    raise BusinessError(
                        "Sélectionnez d'abord votre compte de réserve dans les paramètres."
                    )
                if (
                    manual
                    and connection.last_attempt_at
                    and utc_now() - connection.last_attempt_at < timedelta(seconds=60)
                ):
                    raise BusinessError(
                        "Patientez une minute entre deux synchronisations bancaires."
                    )
                provider_id = connection.provider_account_id
                since = LedgerService(session).account().activation_date
                connection.last_attempt_at = utc_now()
                # Réserve l'échéance avant le réseau, même si le processus est interrompu.
                connection.next_sync_at = (
                    utc_now() + timedelta(hours=connection.interval_hours)
                    if connection.auto_sync_enabled
                    else None
                )
            try:
                connector = self.factory(self.configuration, since=since)
                result = synchronize(self.engine, connector, provider_id)
            except Exception as exc:
                code = exc.code if isinstance(exc, ConnectorError) else "data"
                with Session(self.engine) as session, session.begin():
                    connection = session.get(BankConnection, 1)
                    connection.error_code = code
                    connection.next_sync_at = (
                        utc_now() + timedelta(hours=connection.interval_hours)
                        if connection.auto_sync_enabled
                        else None
                    )
                if isinstance(exc, BusinessError):
                    raise
                raise ConnectorError("unavailable") from None
            with Session(self.engine) as session, session.begin():
                connection = session.get(BankConnection, 1)
                connection.error_code = None
                connection.last_success_at = utc_now()
                connection.next_sync_at = (
                    utc_now() + timedelta(hours=connection.interval_hours)
                    if connection.auto_sync_enabled
                    else None
                )
                reconciliation = LedgerService(session).reconciliation()
            return {**result, "reconciliation": reconciliation}
        finally:
            self.lock.release()

    def run_due(self):
        if not self.configuration.credentials_configured or not self.configuration.module_installed:
            return
        with Session(self.engine) as session:
            connection = session.get(BankConnection, 1)
            due = (
                connection
                and connection.auto_sync_enabled
                and connection.next_sync_at
                and connection.next_sync_at <= utc_now()
                and connection.error_code not in {"credentials", "action_required", "account"}
            )
        if due:
            self.sync(manual=False)

    def start(self):
        def loop():
            while not self.stop.wait(30):
                try:
                    self.run_due()
                except Exception:
                    # Les erreurs attendues sont persistées ; aucun message fournisseur en log.
                    continue

        self.thread = threading.Thread(target=loop, daemon=True, name="bank-sync")
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
