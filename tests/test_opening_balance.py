import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lootsplit.api import create_app
from lootsplit.domain import BusinessError
from lootsplit.models import BankConnection

TOKEN = "opening-balance-test-key-with-more-than-thirty-two-characters"
URL = "/api/account/opening-balance"


@pytest.fixture
def opened(tmp_path):
    app = create_app(tmp_path / "app.db", TOKEN)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        for name, code in (("Vacances", "RES-VAC"), ("Sécurité", "RES-SECU")):
            assert (
                client.post("/api/envelopes", json={"name": name, "code": code}).status_code == 201
            )
        assert (
            client.post(
                "/api/setup",
                json={
                    "activation_date": (date.today() - timedelta(days=2)).isoformat(),
                    "opening_balance_cents": 10000,
                    "allocations": {"1": 10000},
                },
            ).status_code
            == 201
        )
        yield app, client


def body(client, balance=0, allocations=None):
    return {
        "revision": client.get(URL).json()["revision"],
        "opening_balance_cents": balance,
        "allocations": allocations or {},
        "reason": "Virement déjà importé, compté deux fois au démarrage",
        "confirmed": True,
    }


def exported(client):
    return client.get("/api/export/json").json()


def import_credit(client):
    return client.post(
        "/api/import/csv",
        json={
            "content": "booking_date;amount;raw_label;provider_transaction_id\n"
            f"{date.today().isoformat()};100,00;VIR RES-VAC;opening-duplicate\n",
            "bank_balance_cents": 10000,
        },
    )


def test_duplicate_removed_without_changing_bank_history_and_backup_is_previous_state(
    opened, tmp_path
):
    app, client = opened
    assert import_credit(client).status_code == 200
    with Session(app.state.engine) as session, session.begin():
        session.add(BankConnection(id=1, provider_account_id="test-lep", masked_iban="•••• 1234"))
    assert client.get(URL).json()["difference_cents"] == -10000
    previous = exported(client)
    response = client.patch(URL, json=body(client))
    assert response.status_code == 200, response.text
    assert response.json()["reconciliation"]["reconciled"]
    current = exported(client)
    for table in (
        "transactions",
        "external_identities",
        "allocations",
        "bank_connection",
        "envelopes",
    ):
        assert current[table] == previous[table]
    assert current["ledger"][:-1] == previous["ledger"]
    correction = current["ledger"][-1]
    assert correction["kind"] == "INITIAL"
    assert correction["amount_cents"] == -10000
    assert correction["transaction_id"] is None
    account = current["accounts"][0]
    assert correction["effective_date"] == account["activation_date"]
    assert account["current_balance_cents"] == 10000
    assert account["opening_balance_cents"] == 0
    assert account["last_sync_at"] == previous["accounts"][0]["last_sync_at"]
    summary = client.get(f"/api/envelopes/1/summary?year={date.today().year}").json()
    assert summary["in_cents"] == 10000 and summary["out_cents"] == 0
    chart = client.get(f"/api/envelopes/1/chart?year={date.today().year}").json()
    assert chart[-1]["balance_cents"] == 10000
    card = next(e for e in client.get("/api/dashboard").json()["envelopes"] if e["id"] == 1)
    assert card["month_movement_count"] == 1
    assert card["month_net_cents"] == 10000
    assert current["audit"][:-1] == previous["audit"]
    audit = current["audit"][-1]
    assert audit["event_type"] == "CORRECT_OPENING_BALANCE"
    assert json.loads(audit["old_value"])["balance_cents"] == 10000
    assert json.loads(audit["new_value"])["balance_cents"] == 0

    name = response.json()["backup"]["name"]
    download = client.get(f"/api/backups/{name}/download")
    saved = tmp_path / "before-correction.db"
    saved.write_bytes(download.content)
    with closing(sqlite3.connect(saved)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT opening_balance_cents FROM accounts").fetchone()[0] == 10000
        assert db.execute("SELECT SUM(amount_cents) FROM ledger").fetchone()[0] == 20000
    for statement in (
        "UPDATE ledger SET amount_cents=0",
        "DELETE FROM audit_log",
        "UPDATE bank_transactions SET amount_cents=0",
    ):
        with pytest.raises(IntegrityError), app.state.engine.begin() as connection:
            connection.exec_driver_sql(statement)
    assert import_credit(client).json()["duplicates"] == 1
    assert client.get("/api/reconciliation").json()["reconciled"]
    # Une seconde correction part du montant net INITIAL, pas de la première écriture.
    second = client.patch(URL, json=body(client, 48, {"2": 48}))
    assert second.status_code == 200
    assert second.json()["reconciliation"]["difference_cents"] == -48
    preview = client.get(URL).json()
    assert {e["name"]: e["initial_cents"] for e in preview["envelopes"]} == {
        "Vacances": 0,
        "Sécurité": 48,
        "NON AFFECTÉ": 0,
    }


def test_repartition_only_and_unassigned_before_first_import(opened):
    _, client = opened
    response = client.patch(URL, json=body(client, 10000, {"2": 8000}))
    assert response.status_code == 200
    result = response.json()["reconciliation"]
    assert result["reconciled"] and result["unassigned_cents"] == 2000
    assert client.patch(URL, json=body(client, 48)).status_code == 200
    account = client.get("/api/accounts").json()[0]
    assert account["opening_balance_cents"] == account["current_balance_cents"] == 48
    assert client.get("/api/reconciliation").json()["unassigned_cents"] == 48


def test_manual_bank_allocation_survives_initial_correction(opened):
    _, client = opened
    assert import_credit(client).status_code == 200
    assert (
        client.patch("/api/transactions/1/allocation", json={"envelope_id": 2}).status_code == 200
    )
    previous = exported(client)
    assert client.patch(URL, json=body(client)).status_code == 200
    current = exported(client)
    assert current["allocations"] == previous["allocations"]
    assert current["transactions"] == previous["transactions"]
    assert current["ledger"][:-1] == previous["ledger"]
    assert client.get("/api/reconciliation").json()["reconciled"]
    assert {e["name"]: e["balance_cents"] for e in client.get("/api/envelopes").json()} == {
        "Vacances": 0,
        "Sécurité": 10000,
        "NON AFFECTÉ": 0,
    }


@pytest.mark.parametrize(
    "patch,status",
    [
        ({"confirmed": False}, 409),
        ({"confirmed": "true"}, 422),
        ({"reason": "   "}, 409),
        ({"opening_balance_cents": -1}, 422),
        ({"opening_balance_cents": True}, 422),
        ({"allocations": {"1": -1}}, 422),
        ({"allocations": {"1": True}}, 422),
        ({"allocations": {"9999": 0}}, 409),
        ({"allocations": {"3": 0}}, 409),
        ({"allocations": {"1": 1}}, 409),
        ({"opening_balance_cents": 10000, "allocations": {"1": 10000}}, 409),
    ],
)
def test_invalid_correction_preserves_everything(opened, monkeypatch, patch, status):
    app, client = opened

    def no_backup():
        pytest.fail("Les données invalides ne doivent pas créer de sauvegarde")

    monkeypatch.setattr(app.state.backups, "create", no_backup)
    payload = {**body(client), **patch}
    previous = exported(client)
    assert client.patch(URL, json=payload).status_code == status
    assert exported(client) == previous
    assert not app.state.banking.lock.locked()


def test_stale_busy_and_backup_failure_preserve_everything(opened, monkeypatch):
    app, client = opened
    payload = body(client)
    assert client.patch("/api/envelopes/1", json={"name": "Voyages"}).status_code == 200
    previous = exported(client)
    assert client.patch(URL, json=payload).status_code == 409
    payload = body(client)
    app.state.banking.lock.acquire()
    try:
        assert client.patch(URL, json=payload).status_code == 409
    finally:
        app.state.banking.lock.release()

    def fail_backup():
        raise BusinessError("Sauvegarde indisponible")

    monkeypatch.setattr(app.state.backups, "create", fail_backup)
    assert client.patch(URL, json=payload).status_code == 409
    assert exported(client) == previous
    assert not app.state.banking.lock.locked()


def test_archived_initial_allocation_is_preserved(opened):
    _, client = opened
    assert (
        client.post(
            "/api/reallocations",
            json={
                "from_envelope_id": 1,
                "to_envelope_id": 2,
                "amount_cents": 10000,
            },
        ).status_code
        == 201
    )
    assert client.post("/api/envelopes/1/archive").status_code == 200
    previous = exported(client)
    assert client.patch(URL, json=body(client)).status_code == 409
    assert exported(client) == previous
    assert client.patch(URL, json=body(client, 10048, {"1": 10000, "2": 48})).status_code == 200


def test_correction_requires_authentication_csrf_and_initialization(opened, tmp_path):
    _, client = opened
    payload = body(client)
    del client.headers["Authorization"]
    assert client.get(URL).status_code == 401
    assert client.patch(URL, json=payload).status_code == 401
    csrf = client.post("/api/auth/login", json={"token": TOKEN}).json()["csrf_token"]
    assert client.get(URL).status_code == 200
    assert client.patch(URL, json=payload).status_code == 403
    assert client.patch(URL, json=payload, headers={"X-CSRF-Token": csrf}).status_code == 200
    with TestClient(
        create_app(tmp_path / "empty.db", TOKEN), headers={"Authorization": f"Bearer {TOKEN}"}
    ) as empty:
        assert empty.get(URL).status_code == 409
        assert empty.patch(URL, json=payload).status_code == 409
