from datetime import date

import pytest

from lootsplit.domain import (
    BankTransaction,
    BusinessError,
    annual_chart,
    match_code,
    normalize_label,
    parse_euros,
    validate_code,
)


@pytest.mark.parametrize(
    "label,expected",
    [
        ("VIR sépa   res-noel", 1),
        ("VIR (RES-NOEL)", 1),
        ("RES-NOEL2", None),
        ("XRES-NOEL", None),
        ("RES-NOEL-ENF", None),
        ("RES-NOEL_2", None),
        ("RES-NOLE", None),
        ("RES-NOEL / RES-VAC", None),
        ("RES-NOEL RES-NOEL", 1),
        ("INTÉRÊTS COMPTE DE RESERVE", None),
    ],
)
def test_matching_full_tokens_and_ambiguity(label, expected):
    assert match_code(label, {"RES-NOEL": 1, "RES-VAC": 2}) == expected


def test_normalization_and_code_validation():
    assert normalize_label("  intérêts\t compte de réserve ") == "INTERETS COMPTE DE RESERVE"
    assert validate_code(" res-noel ") == "RES-NOEL"
    for code in ("ÉPARGNE", "WITH SPACE", "A" * 21, ""):
        with pytest.raises(BusinessError):
            validate_code(code)


@pytest.mark.parametrize(
    "text,cents",
    [
        ("147,36", 14736),
        ("-800.01", -80001),
        ("1\u202f720,00", 172000),
        ("0.01", 1),
        ("0", 0),
    ],
)
def test_exact_money(text, cents):
    assert parse_euros(text) == cents


@pytest.mark.parametrize("text", ["NaN", "Infinity", "1,001", "abc", "1e30"])
def test_invalid_money(text):
    with pytest.raises(BusinessError):
        parse_euros(text)


def test_bank_transaction_rejects_float_and_other_currency():
    with pytest.raises(BusinessError):
        BankTransaction(date(2026, 10, 1), 1.2, "Test")
    with pytest.raises(BusinessError):
        BankTransaction(date(2026, 10, 1), 100, "Test", currency="USD")


def test_chart_carries_balance_over_year_and_stops_today():
    entries = [
        (date(2026, 9, 30), 10000),
        (date(2026, 12, 31), 11500),
        (date(2027, 1, 5), -500),
    ]
    previous = annual_chart(entries, 2026, date(2027, 1, 20))
    assert len(previous) == 12
    assert previous[-1] == {"date": "2026-12-31", "balance_cents": 21500}
    assert annual_chart(entries, 2027, date(2027, 1, 20)) == [
        {"date": "2027-01-20", "balance_cents": 21000}
    ]
    assert annual_chart(entries, 2028, date(2027, 1, 20)) == []
