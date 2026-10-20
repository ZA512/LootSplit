"""Règles pures : aucun accès SQL, HTTP ou bancaire."""

import calendar
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

MAX_CENTS = 10**12
CODE = re.compile(r"[A-Z0-9_-]{1,20}\Z")


class BusinessError(ValueError):
    pass


def validate_cents(amount: int) -> int:
    if type(amount) is not int or abs(amount) > MAX_CENTS:
        raise BusinessError("Un montant doit être un entier en centimes dans les limites.")
    return amount


def normalize_label(label: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", label) if not unicodedata.combining(c))
    return " ".join(plain.upper().split())


def validate_code(value: str) -> str:
    code = value.strip().upper()
    if not CODE.fullmatch(code):
        raise BusinessError("Code : 1 à 20 caractères parmi A-Z, 0-9, - et _.")
    return code


def match_code(label: str, active_codes: dict[str, int]) -> int | None:
    normalized = normalize_label(label)
    matches = {
        envelope_id
        for code, envelope_id in active_codes.items()
        if re.search(r"(?<![A-Z0-9_-])" + re.escape(code) + r"(?![A-Z0-9_-])", normalized)
    }
    # Plusieurs codes sont ambigus : qualification manuelle obligatoire.
    return next(iter(matches)) if len(matches) == 1 else None


def parse_euros(value: str) -> int:
    cleaned = value.replace("\u202f", "").replace("\xa0", "").replace(" ", "")
    try:
        amount = Decimal(cleaned.replace(",", "."))
        if not amount.is_finite() or abs(amount) > Decimal(MAX_CENTS) / 100:
            raise BusinessError("Montant hors limites.")
        cents = amount * 100
        if cents != cents.to_integral_value():
            raise BusinessError("Deux décimales au maximum sont autorisées.")
        return int(cents)
    except InvalidOperation as exc:
        raise BusinessError("Montant invalide.") from exc


@dataclass(frozen=True)
class BankTransaction:
    booking_date: date
    amount_cents: int
    raw_label: str
    value_date: date | None = None
    provider_transaction_id: str | None = None
    currency: str = "EUR"

    def __post_init__(self):
        validate_cents(self.amount_cents)
        if self.currency != "EUR":
            raise BusinessError("Seules les transactions en EUR sont acceptées.")
        if not self.raw_label.strip() or len(self.raw_label) > 2000:
            raise BusinessError("Libellé vide ou trop long.")

    def fingerprint(self, account_id: int) -> str:
        fields = [
            account_id,
            self.booking_date.isoformat(),
            self.value_date.isoformat() if self.value_date else None,
            self.amount_cents,
            self.raw_label,
            self.currency,
        ]
        return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()


def annual_chart(
    entries: list[tuple[date, int]], year: int, today: date
) -> list[dict[str, str | int]]:
    """Soldes de clôture ; le point du mois courant correspond au jour courant."""
    if year > today.year:
        return []
    points = []
    for month in range(1, 13):
        end = date(year, month, calendar.monthrange(year, month)[1])
        end = min(end, today)
        if end.year != year or (year == today.year and month > today.month):
            break
        points.append(
            {
                "date": end.isoformat(),
                "balance_cents": sum(amount for day, amount in entries if day <= end),
            }
        )
    return points
