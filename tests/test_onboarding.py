"""Le démarrage bancaire publie tout ensemble, sans réinitialiser un compte existant."""

import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from lootsplit.api import create_app


@pytest.fixture
def setup_client(tmp_path):
    class Connector:
        def __init__(self, *args):
            pass

        def discover(self):
            return [
                {
                    "id": "secret-provider-id",
                    "name": "LEP",
                    "masked_iban": "•••• 1234",
                    "balance_cents": 12500,
                }
            ]

    app = create_app(tmp_path / "app.db", "a" * 40)
    with TestClient(app, headers={"Authorization": "Bearer " + "a" * 40}) as client:
        app.state.banking.factory = Connector
        yield client, app.state.banking


def body(**changes):
    return {
        "name": "LEP",
        "activation_date": (date.today() - timedelta(days=1)).isoformat(),
        "opening_balance_cents": 10000,
        "envelopes": [{"name": "Vacances", "code": "RES-VAC", "amount_cents": 8000}],
        **changes,
    }


def test_discover_before_setup_then_publish_selected_bank_atomically(setup_client):
    client, banking = setup_client
    choice = client.post("/api/banking/accounts").json()[0]
    assert "secret-provider-id" not in str(choice)
    assert client.get("/api/accounts").json() == []
    result = client.post(
        "/api/setup",
        json=body(bank_choice_id=choice["choice_id"], bank_confirmed=True, auto_sync_enabled=True),
    )
    assert result.status_code == 201, result.text
    assert result.json()["unassigned_cents"] == 2000
    account = client.get("/api/accounts").json()[0]
    # Le solde actuel découvert ne remplace pas le solde de clôture confirmé.
    assert account["current_balance_cents"] == 10000
    status = client.get("/api/banking/status").json()
    assert status["connected"] and status["auto_sync_enabled"] and status["next_sync_at"]
    assert status["last_success_at"] is None
    assert choice["choice_id"] not in banking.choices
    assert client.post("/api/setup", json=body()).status_code == 409
    assert len(client.get("/api/envelopes").json()) == 2


@pytest.mark.parametrize("failure", ["expired", "unconfirmed", "overspent", "duplicate"])
def test_setup_failure_leaves_no_account_envelope_or_bank_connection(setup_client, failure):
    client, banking = setup_client
    choice_id = client.post("/api/banking/accounts").json()[0]["choice_id"]
    request = body(bank_choice_id=choice_id, bank_confirmed=True)
    if failure == "expired":
        _, item = banking.choices[choice_id]
        banking.choices[choice_id] = (time.monotonic() - 1, item)
    elif failure == "unconfirmed":
        request["bank_confirmed"] = False
    elif failure == "overspent":
        request["envelopes"][0]["amount_cents"] = 10001
    else:
        request["envelopes"].append(request["envelopes"][0].copy())
    assert client.post("/api/setup", json=request).status_code == 409
    assert client.get("/api/accounts").json() == []
    assert client.get("/api/envelopes").json() == []
    assert not client.get("/api/banking/status").json()["connected"]
    if failure in {"overspent", "duplicate"}:
        assert (
            client.post(
                "/api/setup", json=body(bank_choice_id=choice_id, bank_confirmed=True)
            ).status_code
            == 201
        )


def test_csv_setup_and_locked_setup(setup_client):
    client, banking = setup_client
    banking.lock.acquire()
    try:
        assert client.post("/api/setup", json=body()).status_code == 409
    finally:
        banking.lock.release()
    assert client.post("/api/setup", json=body()).status_code == 201
    assert not client.get("/api/banking/status").json()["connected"]


def test_setup_rejects_conflicting_or_non_integer_payload(setup_client):
    client, _ = setup_client
    assert client.post("/api/setup", json=body(allocations={"1": 10})).status_code == 422
    assert client.post("/api/setup", json=body(auto_sync_enabled=True)).status_code == 422
    request = body()
    request["envelopes"][0]["amount_cents"] = 1.5
    assert client.post("/api/setup", json=request).status_code == 422


def test_resume_previously_created_envelopes_without_partial_edits(setup_client):
    client, _ = setup_client
    envelope = client.post("/api/envelopes", json={"name": "Ancien nom", "code": "RES-VAC"}).json()
    request = body()
    request["envelopes"][0]["existing_id"] = envelope["id"]
    request["envelopes"][0]["amount_cents"] = 10001
    assert client.post("/api/setup", json=request).status_code == 409
    assert client.get("/api/envelopes").json()[0]["name"] == "Ancien nom"
    request["envelopes"][0]["amount_cents"] = 8000
    assert client.post("/api/setup", json=request).status_code == 201
    values = client.get("/api/envelopes").json()
    assert len(values) == 2 and values[0]["name"] == "Vacances"
    assert values[0]["balance_cents"] == 8000
