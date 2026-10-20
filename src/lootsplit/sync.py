"""Récupération hors transaction SQL, import atomique et erreur sans secrets."""

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from lootsplit.connectors import BankConnector
from lootsplit.domain import BusinessError
from lootsplit.models import Account
from lootsplit.service import LedgerService


def synchronize(engine: Engine, connector: BankConnector, provider_account_id: str):
    with Session(engine) as session:
        start = LedgerService(session).account().activation_date
    try:
        # Une panne réseau n'immobilise pas le verrou d'écriture SQLite.
        balance = connector.get_balance(provider_account_id)
        transactions = connector.get_transactions(provider_account_id, start)
        with Session(engine) as session, session.begin():
            return LedgerService(session, actor="SYSTEM").import_transactions(
                transactions, connector.source, balance
            )
    except Exception as exc:
        # Ne jamais persister un message du fournisseur : il pourrait contenir des secrets.
        message = "Synchronisation impossible. Les données existantes sont conservées."
        with Session(engine) as session, session.begin():
            session.get(Account, 1).last_sync_error = message
        if isinstance(exc, BusinessError):
            raise
        raise BusinessError(message) from None
