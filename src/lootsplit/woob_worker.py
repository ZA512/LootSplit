"""Processus court Woob. Aucune configuration ni session bancaire écrite sur disque."""

import contextlib
import json
import logging
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal

from woob.capabilities.bank import Account
from woob.capabilities.base import empty
from woob.core import WoobBase
from woob.exceptions import (
    ActionNeeded,
    AppValidation,
    BrowserIncorrectPassword,
    BrowserQuestion,
    NeedInteractive,
)
from woob.tools.backend import Module

from lootsplit.domain import BusinessError, normalize_label, parse_euros
from lootsplit.woob_connector import ConnectorError


def euro_cents(value) -> int:
    if empty(value) or isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise ConnectorError("data")
    return parse_euros(str(value))


def bank_date(value, optional=False) -> str | None:
    if empty(value) and optional:
        return None
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        raise ConnectorError("data")
    return value.isoformat()


def livret_a(account) -> bool:
    return (
        account.type == Account.TYPE_SAVINGS
        and account.currency == "EUR"
        and bool(re.search(r"\bLIVRET\s+A\b", normalize_label(account.label)))
    )


def account_data(account):
    iban = getattr(account, "iban", None)
    return {
        "id": account.id,
        "name": "Livret A",
        "balance_cents": euro_cents(account.balance),
        "masked_iban": "•••• " + str(iban)[-4:]
        if not empty(iban)
        else "Compte •••• " + str(account.id)[-4:],
    }


def collect(backend, request: dict):
    accounts = [account for account in backend.iter_accounts() if livret_a(account)]
    if request["operation"] == "accounts":
        return [account_data(account) for account in accounts]
    if request["operation"] != "snapshot":
        raise ConnectorError("data")
    account = next((a for a in accounts if a.id == request["account_id"]), None)
    if account is None:
        raise ConnectorError("account")
    start = date.fromisoformat(request["since"])
    transactions = []
    for item in backend.iter_history(account):
        if getattr(item, "coming", False) is True:
            continue
        booked = bank_date(item.date)
        if date.fromisoformat(booked) <= start:
            continue  # Ne jamais interrompre : l'ordre du fournisseur n'est pas garanti.
        currency = getattr(item, "currency", None)
        if not empty(currency) and currency != "EUR":
            raise ConnectorError("data")
        raw = item.raw if not empty(item.raw) else item.label
        if empty(raw):
            raise ConnectorError("data")
        transactions.append(
            {
                "booking_date": booked,
                "value_date": bank_date(item.vdate, optional=True),
                "amount_cents": euro_cents(item.amount),
                "raw_label": raw,
                "provider_transaction_id": str(item.id) if not empty(item.id) else None,
            }
        )
        if len(transactions) > 20_000:
            raise ConnectorError("data")
    return {"balance_cents": euro_cents(account.balance), "transactions": transactions}


def execute(request: dict):
    # WoobBase ne télécharge pas de modules et ne lit pas un fichier de backends.
    core = WoobBase(modules_path=request["modules_path"])
    try:
        try:
            backend = core.load_backend(
                "cragr",
                "lootsplit",
                params={
                    "website": request["website"],
                    "login": request["login"],
                    "password": request["password"],
                },
            )
        except Module.ConfigError:
            raise ConnectorError("configuration") from None
        return collect(backend, request)
    finally:
        core.deinit()


def main():
    logging.disable(logging.CRITICAL)
    try:
        request = json.loads(sys.stdin.read())
        with (
            open(os.devnull, "w") as sink,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            data = execute(request)
        response = {"ok": True, "data": data}
    except ConnectorError as exc:
        response = {"ok": False, "error": exc.code}
    except BusinessError:
        response = {"ok": False, "error": "data"}
    except BrowserIncorrectPassword:
        response = {"ok": False, "error": "credentials"}
    except (ActionNeeded, AppValidation, BrowserQuestion, NeedInteractive):
        response = {"ok": False, "error": "action_required"}
    except Exception:
        response = {"ok": False, "error": "unavailable"}
    print(json.dumps(response))


if __name__ == "__main__":
    main()
