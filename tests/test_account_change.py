import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lootsplit.api import create_app
from lootsplit.database import IMMUTABLE_TRIGGERS
from lootsplit.domain import BusinessError
from lootsplit.models import BankConnection

TOKEN = "account-change-test-token-at-least-thirty-two-characters"


@pytest.fixture
def account_client(tmp_path):
    app = create_app(tmp_path / "app.db", TOKEN)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        vacation = client.post(
            "/api/envelopes", json={"name": "Vacances", "code": "RES-VAC", "icon": "sun"}
        ).json()
        client.post("/api/envelopes", json={"name": "Sécurité", "code": "RES-SECU"})
        archived = client.post(
            "/api/envelopes", json={"name": "Ancienne réserve", "code": "RES-OLD"}
        ).json()
        result = client.post(
            "/api/setup",
            json={
                "activation_date": (date.today() - timedelta(days=3)).isoformat(),
                "opening_balance_cents": 12345,
                "allocations": {str(vacation["id"]): 10000},
            },
        )
        assert result.status_code == 201
        assert client.post(f"/api/envelopes/{archived['id']}/archive").status_code == 200
        imported = client.post(
            "/api/import/csv",
            json={
                "content": f"booking_date;amount;raw_label;provider_transaction_id\n"
                f"{date.today().isoformat()};10,00;VIR RES-VAC;old-bank-operation\n",
                "bank_balance_cents": 13345,
            },
        )
        assert imported.status_code == 200
        with Session(app.state.engine) as session, session.begin():
            session.add(
                BankConnection(
                    id=1,
                    provider_account_id="private-old-bank-id",
                    masked_iban="•••• 1234",
                    auto_sync_enabled=True,
                    interval_hours=12,
                )
            )
        app.state.banking.choices["old-choice"] = (float("inf"), {"id": "stale"})
        yield app, client


def change_body(client):
    response = client.get("/api/account/change-preview")
    assert response.status_code == 200
    return {
        "revision": response.json()["revision"],
        "amounts_recorded": True,
        "confirmation": "CHANGER DE COMPTE",
    }


def test_change_preserves_definitions_and_backup_then_allows_new_account(account_client, tmp_path):
    app, client = account_client
    previous = client.get("/api/export/json").json()
    preview = client.get("/api/account/change-preview").json()
    assert preview["masked_iban"] == "•••• 1234"
    assert preview["bank_balance_cents"] == 13345
    assert preview["transaction_count"] == 1
    assert preview["difference_cents"] == 0
    assert {e["name"]: e["balance_cents"] for e in preview["envelopes"]} == {
        "Vacances": 11000,
        "Sécurité": 0,
        "Ancienne réserve": 0,
        "NON AFFECTÉ": 2345,
    }
    assert "private-old-bank-id" not in json.dumps(preview)

    response = client.post("/api/account/change", json=change_body(client))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["requires_setup"]
    assert not app.state.banking.choices
    assert not app.state.banking.lock.locked()
    assert client.get("/api/accounts").json() == []
    remaining = client.get("/api/envelopes?include_archived=true").json()
    expected = [e for e in previous["envelopes"] if not e["is_system"]]
    assert [e["id"] for e in remaining] == [e["id"] for e in expected]
    assert all(e["balance_cents"] == 0 for e in remaining)
    assert next(e for e in remaining if e["code"] == "RES-OLD")["status"] == "ARCHIVED"
    assert next(e for e in remaining if e["code"] == "RES-VAC")["icon"] == "sun"
    current = client.get("/api/export/json").json()
    for name in ("transactions", "allocations", "ledger", "external_identities", "bank_connection"):
        assert current[name] == []
    assert [a["event_type"] for a in current["audit"]] == ["CHANGE_RESERVE_ACCOUNT"]
    status = client.get("/api/banking/status").json()
    assert not status["connected"] and not status["auto_sync_enabled"]
    assert client.post("/api/sync").status_code == 409
    assert client.post("/api/account/change", json=change_body_for(preview)).status_code == 409

    downloaded = client.get(f"/api/backups/{result['backup']['name']}/download")
    assert downloaded.status_code == 200
    saved = tmp_path / "before-change.db"
    saved.write_bytes(downloaded.content)
    with closing(sqlite3.connect(saved)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT current_balance_cents FROM accounts").fetchone()[0] == 13345
        assert db.execute("SELECT COUNT(*) FROM bank_transactions").fetchone()[0] == 1
        assert db.execute("SELECT SUM(amount_cents) FROM ledger").fetchone()[0] == 13345
        assert (
            db.execute("SELECT provider_account_id FROM bank_connection").fetchone()[0]
            == "private-old-bank-id"
        )

    setup = client.post(
        "/api/setup",
        json={
            "activation_date": date.today().isoformat(),
            "opening_balance_cents": 48,
            "allocations": {},
        },
    )
    assert setup.status_code == 201
    assert setup.json()["unassigned_cents"] == 48
    assert setup.json()["reconciled"]
    assert client.post("/api/account/change", json=change_body_for(preview)).status_code == 409
    choices = client.post(
        "/api/banking/selection", json={"choice_id": "old-choice", "confirmed": True}
    )
    assert choices.status_code == 409
    app.state.banking.choices["new-choice"] = (
        float("inf"),
        {"id": "new-bank-id", "name": "LEP", "masked_iban": "•••• 9876"},
    )
    selected = client.post(
        "/api/banking/selection", json={"choice_id": "new-choice", "confirmed": True}
    )
    assert selected.status_code == 200
    assert selected.json()["masked_iban"] == "•••• 9876"
    assert not selected.json()["auto_sync_enabled"]
    with pytest.raises(IntegrityError):
        with app.state.engine.begin() as connection:
            connection.exec_driver_sql("DELETE FROM ledger")


def change_body_for(preview):
    return {
        "revision": preview["revision"],
        "amounts_recorded": True,
        "confirmation": "CHANGER DE COMPTE",
    }


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("confirmation", "", 409),
        ("confirmation", "CHANGER", 409),
        ("amounts_recorded", False, 409),
        ("amounts_recorded", "true", 422),
        ("revision", "invalid", 422),
    ],
)
def test_confirmation_is_required_before_any_backup_or_change(account_client, field, value, code):
    app, client = account_client
    previous = client.get("/api/export/json").json()
    body = change_body(client)
    body[field] = value
    response = client.post("/api/account/change", json=body)
    assert response.status_code == code
    assert client.get("/api/export/json").json() == previous
    assert not app.state.backups.files()


def test_change_rejects_stale_summary_and_active_bank_connection(account_client):
    app, client = account_client
    body = change_body(client)
    client.post("/api/envelopes", json={"name": "Nouvelle enveloppe", "code": "RES-NEW"})
    response = client.post("/api/account/change", json=body)
    assert response.status_code == 409 and "données ont changé" in response.text
    body = change_body(client)
    with app.state.banking.lock:
        response = client.post("/api/account/change", json=body)
    assert response.status_code == 409 and "connexion bancaire" in response.text
    assert not app.state.backups.files()
    assert client.get("/api/accounts").json()[0]["current_balance_cents"] == 13345


def test_failed_backup_keeps_all_data(account_client, monkeypatch):
    app, client = account_client
    previous = client.get("/api/export/json").json()

    def fail():
        raise BusinessError("La sauvegarde a échoué.")

    monkeypatch.setattr(app.state.backups, "create", fail)
    response = client.post("/api/account/change", json=change_body(client))
    assert response.status_code == 409
    assert client.get("/api/export/json").json() == previous
    assert not app.state.banking.lock.locked()
    assert "old-choice" in app.state.banking.choices


def test_failure_after_deletes_rolls_back_rows_and_immutability_triggers(
    account_client, monkeypatch
):
    import lootsplit.account_change as account_change

    app, client = account_client
    previous = client.get("/api/export/json").json()

    def fail(_):
        raise RuntimeError("Simulated failure after deletion")

    monkeypatch.setattr(account_change, "protect_history", fail)
    with pytest.raises(RuntimeError, match="Simulated failure"):
        client.post("/api/account/change", json=change_body(client))
    assert client.get("/api/export/json").json() == previous
    assert not app.state.banking.lock.locked()
    with app.state.engine.connect() as connection:
        triggers = set(
            connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).scalars()
        )
    assert set(IMMUTABLE_TRIGGERS) <= triggers
    with pytest.raises(IntegrityError):
        with app.state.engine.begin() as connection:
            connection.exec_driver_sql("DELETE FROM bank_transactions")


def test_account_change_authentication_and_csrf(account_client):
    _, client = account_client
    body = change_body(client)
    del client.headers["Authorization"]
    assert client.get("/api/account/change-preview").status_code == 401
    assert client.post("/api/account/change", json=body).status_code == 401
    login = client.post("/api/auth/login", json={"token": TOKEN}).json()
    assert client.get("/api/account/change-preview").status_code == 200
    assert client.post("/api/account/change", json=body).status_code == 403
    result = client.post(
        "/api/account/change", json=body, headers={"X-CSRF-Token": login["csrf_token"]}
    )
    assert result.status_code == 200
