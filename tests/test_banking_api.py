import json
from datetime import date, timedelta

import pytest

from lootsplit.domain import BankTransaction
from lootsplit.woob_connector import BankConfiguration, ConnectorError


def test_bank_routes_require_authentication_and_preserve_local_mode(tmp_path):
    from fastapi.testclient import TestClient

    from lootsplit.api import create_app

    with TestClient(create_app(tmp_path / "app.db", "a" * 40)) as client:
        assert client.get("/api/banking/status").status_code == 401
        assert client.post("/api/sync").status_code == 401
        headers = {"Authorization": "Bearer " + "a" * 40}
        status = client.get("/api/banking/status", headers=headers).json()
        assert not status["configured"] and not status["connected"]
        assert client.post("/api/banking/accounts", headers=headers).status_code == 409
        assert client.post("/api/sync", headers=headers).status_code == 409


@pytest.mark.parametrize("name", ["Livret A", "LEP"])
def test_bank_selection_sync_schedule_and_error_state(tmp_path, name):
    from fastapi.testclient import TestClient

    from lootsplit.api import create_app

    class Connector:
        source = "woob"
        failure = False

        def __init__(self, *args, **kwargs):
            pass

        def discover(self):
            return [
                {
                    "id": "private-account",
                    "name": name,
                    "masked_iban": "•••• 4321",
                    "balance_cents": 10100,
                }
            ]

        def get_balance(self, account_id):
            if self.failure:
                raise ConnectorError("credentials")
            return 10100

        def get_transactions(self, account_id, since):
            return [BankTransaction(date.today(), 100, "RES-VAC", provider_transaction_id="1")]

    app = create_app(tmp_path / "app.db", "a" * 40)
    (tmp_path / "cragr").mkdir()
    (tmp_path / "cragr" / "module.py").touch()
    with TestClient(app, headers={"Authorization": "Bearer " + "a" * 40}) as client:
        app.state.banking.factory = Connector
        app.state.banking.configuration = BankConfiguration(
            "www.ca-paris.fr", "12345678901", "secret-password", tmp_path
        )
        assert (
            client.post("/api/envelopes", json={"name": "Vacances", "code": "RES-VAC"}).status_code
            == 201
        )
        assert (
            client.post(
                "/api/setup",
                json={
                    "name": name,
                    "activation_date": (date.today() - timedelta(days=1)).isoformat(),
                    "opening_balance_cents": 10000,
                    "allocations": {"1": 10000},
                },
            ).status_code
            == 201
        )
        assert client.get("/api/accounts").json()[0]["name"] == name
        choice = client.post("/api/banking/accounts").json()[0]
        assert choice["name"] == name
        assert "private-account" not in json.dumps(choice)
        assert (
            client.post(
                "/api/banking/selection",
                json={
                    "choice_id": choice["choice_id"],
                    "confirmed": True,
                },
            ).status_code
            == 200
        )
        account = client.get("/api/accounts").json()[0]
        assert account["name"] == name
        assert account["opening_balance_cents"] == account["current_balance_cents"] == 10000
        for hours in (0, 169, 6.5):
            assert (
                client.patch(
                    "/api/banking/schedule",
                    json={
                        "enabled": True,
                        "interval_hours": hours,
                    },
                ).status_code
                == 422
            )
        assert (
            client.patch(
                "/api/banking/schedule",
                json={
                    "enabled": True,
                    "interval_hours": 6,
                },
            ).status_code
            == 200
        )
        result = client.post("/api/sync")
        assert result.status_code == 200 and result.json()["imported"] == 1
        assert result.json()["reconciliation"]["reconciled"]
        public = client.get("/api/banking/status").json()
        assert public["auto_sync_enabled"] and public["last_success_at"]
        assert "secret-password" not in json.dumps(public)
        exported = client.get("/api/export/json").json()
        assert exported["schema_version"] == 2
        assert exported["bank_connection"][0]["provider_account_id"] == "private-account"
        assert "secret-password" not in json.dumps(exported)
