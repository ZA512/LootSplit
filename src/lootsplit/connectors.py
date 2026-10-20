"""Contrat de lecture bancaire et adaptateur CSV, sans dépendance métier à Woob."""

import csv
import io
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from lootsplit.domain import BankTransaction, BusinessError, parse_euros


@dataclass(frozen=True)
class ConnectorAccount:
    id: str
    name: str
    currency: str = "EUR"


class BankConnector(Protocol):
    source: str

    def get_accounts(self) -> list[ConnectorAccount]: ...
    def get_balance(self, account_id: str) -> int: ...
    def get_transactions(self, account_id: str, since: date) -> list[BankTransaction]: ...


class CsvConnector:
    """Format explicite de secours, distinct d'un parseur spécifique au Crédit Agricole."""

    source = "csv"

    def __init__(self, content: str, balance_cents: int, account_id: str = "1"):
        self.account_id = account_id
        self.balance_cents = balance_cents
        self.transactions = self.parse(content)

    def get_accounts(self) -> list[ConnectorAccount]:
        return [ConnectorAccount(self.account_id, "Livret A")]

    def get_balance(self, account_id: str) -> int:
        self._check_account(account_id)
        return self.balance_cents

    def get_transactions(self, account_id: str, since: date) -> list[BankTransaction]:
        self._check_account(account_id)
        return [t for t in self.transactions if t.booking_date > since]

    def _check_account(self, account_id: str):
        if account_id != self.account_id:
            raise BusinessError("Compte CSV inconnu.")

    @staticmethod
    def parse(content: str) -> list[BankTransaction]:
        if len(content.encode("utf-8")) > 2_000_000:
            raise BusinessError("CSV limité à 2 Mo.")
        stream = io.StringIO(content.lstrip("\ufeff"), newline="")
        reader = csv.DictReader(stream, delimiter=";", strict=True)
        required = {"booking_date", "amount", "raw_label"}
        try:
            headers = reader.fieldnames
        except csv.Error as exc:
            raise BusinessError("En-tête CSV invalide.") from exc
        if not headers or not required.issubset(headers):
            raise BusinessError("Colonnes requises : booking_date;amount;raw_label.")
        if len(set(headers)) != len(headers):
            raise BusinessError("En-tête CSV : les noms de colonnes doivent être uniques.")
        transactions = []
        try:
            for line, row in enumerate(reader, 2):
                if None in row or any(row.get(key) is None for key in required):
                    raise BusinessError(f"CSV ligne {line} : nombre de colonnes invalide.")
                transactions.append(
                    BankTransaction(
                        booking_date=date.fromisoformat(row["booking_date"]),
                        value_date=date.fromisoformat(row["value_date"])
                        if row.get("value_date")
                        else None,
                        amount_cents=parse_euros(row["amount"]),
                        raw_label=row["raw_label"],
                        provider_transaction_id=row.get("provider_transaction_id") or None,
                        currency=row.get("currency") or "EUR",
                    )
                )
                if len(transactions) > 10_000:
                    raise BusinessError("CSV limité à 10 000 transactions.")
        except (ValueError, csv.Error) as exc:
            raise BusinessError(f"CSV invalide à la ligne {reader.line_num} : {exc}") from exc
        return transactions
