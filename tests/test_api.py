import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from lootsplit.api import create_app

TOKEN = "test-token-that-is-longer-than-32-characters"


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "api.db", TOKEN)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client


def setup(client):
    holidays = client.post("/api/envelopes", json={"name": "Vacances", "code": "RES-VAC"})
    assert holidays.status_code == 201, holidays.text
    envelope_id = holidays.json()["id"]
    result = client.post(
        "/api/setup",
        json={
            "activation_date": (date.today() - timedelta(days=3)).isoformat(),
            "opening_balance_cents": 100000,
            "allocations": {str(envelope_id): 80000},
        },
    )
    assert result.status_code == 201, result.text
    return envelope_id


def test_authentication_and_no_data_without_token(client):
    assert client.get("/health", headers={"Authorization": ""}).status_code == 200
    assert client.get("/api/accounts", headers={"Authorization": ""}).status_code == 401
    assert (
        client.get("/api/export/json", headers={"Authorization": "Bearer wrong"}).status_code == 401
    )
    assert client.get("/api/accounts").json() == []


def test_api_end_to_end_and_exports(client):
    envelope_id = setup(client)
    day = (date.today() - timedelta(days=1)).isoformat()
    content = f"booking_date;amount;raw_label;provider_transaction_id\n{day};115,01;VIR RES-VAC;1\n"
    body = {"content": content, "bank_balance_cents": 111501}
    result = client.post("/api/import/csv", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["reconciliation"]["reconciled"]
    assert client.post("/api/import/csv", json=body).json()["duplicates"] == 1
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    card = next(e for e in dashboard.json()["envelopes"] if e["id"] == envelope_id)
    assert card["balance_cents"] == 91501
    transaction_id = client.get("/api/transactions").json()[0]["id"]
    system = next(e for e in dashboard.json()["envelopes"] if e["is_system"])
    response = client.patch(
        f"/api/transactions/{transaction_id}/allocation", json={"envelope_id": system["id"]}
    )
    assert response.status_code == 200, response.text
    assert len(client.get("/api/transactions/unassigned").json()) == 1
    assert client.get("/api/transactions").json()[0]["envelope_name"] == "NON AFFECTÉ"
    assert client.get("/api/reconciliation").json()["reconciled"]
    data = client.get("/api/export/json")
    assert data.headers["cache-control"] == "no-store"
    assert data.json()["transactions"][0]["amount_cents"] == 11501
    assert len(data.json()["allocations"]) == 1
    assert "ADMIN" in json.dumps(data.json()["audit"])
    assert client.get("/api/export/csv").text.startswith("\ufeffdate;")
    assert client.get(f"/api/envelopes/{envelope_id}/history").status_code == 200
    assert (
        client.get(f"/api/envelopes/{envelope_id}/chart?year={date.today().year}").status_code
        == 200
    )


@pytest.mark.parametrize("amount", [1.5, "100", True, 10**15])
def test_no_coercion_of_money(client, amount):
    response = client.post(
        "/api/setup",
        json={
            "activation_date": date.today().isoformat(),
            "opening_balance_cents": amount,
            "allocations": {},
        },
    )
    assert response.status_code == 422


def test_invalid_import_has_no_partial_effect(client):
    setup(client)
    day = date.today().isoformat()
    response = client.post(
        "/api/import/csv",
        json={
            "content": f"booking_date;amount;raw_label\n{day};10;RES-VAC\n{day};bad;ERROR",
            "bank_balance_cents": 101000,
        },
    )
    assert response.status_code == 409
    assert client.get("/api/transactions").json() == []
    assert client.get("/api/reconciliation").json()["bank_balance_cents"] == 100000


def test_input_and_system_envelope_protections(client):
    envelope_id = setup(client)
    assert client.patch(f"/api/envelopes/{envelope_id}", json={"code": None}).status_code == 422
    assert (
        client.patch(f"/api/envelopes/{envelope_id}", json={"status": "ARCHIVED"}).status_code
        == 422
    )
    assert client.post(f"/api/envelopes/{envelope_id}/archive").status_code == 409
    assert (
        client.post(
            "/api/setup",
            json={
                "activation_date": date.today().isoformat(),
                "opening_balance_cents": 0,
                "allocations": {},
            },
        ).status_code
        == 409
    )


def test_startup_requires_strong_token(tmp_path):
    with pytest.raises(RuntimeError, match="32"):
        with TestClient(create_app(tmp_path / "unsafe.db", "short")):
            pass


def test_movement_filters_pagination_and_envelope_year_summary(client):
    envelope_id = setup(client)
    date_value = (date.today() - timedelta(days=1)).isoformat()
    response = client.post(
        "/api/import/csv",
        json={
            "content": f"booking_date;amount;raw_label;provider_transaction_id\n"
            f"{date_value};115,01;VIR RES-VAC;1\n"
            f"{date_value};-15,01;VIR RES-VAC;2\n",
            "bank_balance_cents": 110000,
        },
    )
    assert response.status_code == 200
    movements = client.get("/api/movements?kind=BANK&min_cents=1&limit=1").json()
    assert movements["total"] == 1
    assert movements["items"][0]["amount_cents"] == 11501
    assert movements["items"][0]["envelope_name"] == "Vacances"
    negatives = client.get("/api/movements?max_cents=-1").json()
    assert negatives["total"] == 1
    assert client.get("/api/movements?kind=UNKNOWN").status_code == 422
    assert client.get("/api/movements?text=does-not-exist").json()["total"] == 0
    summary = client.get(f"/api/envelopes/{envelope_id}/summary?year={date.today().year}").json()
    assert summary["balance_cents"] == 90000
    assert summary["in_cents"] == 11501
    assert summary["out_cents"] == -1501
