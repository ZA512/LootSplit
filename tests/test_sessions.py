import time

import pytest
from fastapi.testclient import TestClient

from lootsplit.api import create_app
from lootsplit.auth import COOKIE, Session, Sessions

TOKEN = "test-administrator-key-with-more-than-32-characters"


@pytest.fixture
def browser(tmp_path):
    with TestClient(create_app(tmp_path / "sessions.db", TOKEN)) as browser:
        yield browser


def test_session_cookie_is_http_only_and_mutations_require_csrf(browser):
    assert browser.get("/api/auth/session").status_code == 401
    login = browser.post("/api/auth/login", json={"token": TOKEN})
    assert login.status_code == 200
    cookie = login.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and TOKEN not in cookie
    csrf = login.json()["csrf_token"]
    assert browser.get("/api/auth/session").json()["csrf_token"] == csrf
    assert browser.get("/api/accounts").status_code == 200
    assert browser.post("/api/sync").status_code == 403
    assert browser.post("/api/banking/accounts").status_code == 403
    payload = {"name": "Vacances", "code": "RES-VAC"}
    assert browser.post("/api/envelopes", json=payload).status_code == 403
    assert (
        browser.post("/api/envelopes", json=payload, headers={"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    assert (
        browser.post("/api/envelopes", json=payload, headers={"X-CSRF-Token": csrf}).status_code
        == 201
    )
    assert browser.post("/api/auth/logout").status_code == 403
    old_cookie = browser.cookies.get(COOKIE)
    assert browser.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert browser.get("/api/accounts").status_code == 401
    browser.cookies.set(COOKIE, old_cookie)
    assert browser.get("/api/accounts").status_code == 401


def test_bad_key_and_login_throttling(browser):
    for _ in range(10):
        assert browser.post("/api/auth/login", json={"token": "wrong"}).status_code == 401
    assert browser.post("/api/auth/login", json={"token": TOKEN}).status_code == 429


def test_expired_session_is_rejected():
    sessions = Sessions()
    cookie, _ = sessions.login("test", TOKEN, TOKEN)
    sessions._sessions[sessions.key(cookie)] = Session("csrf", time.monotonic() - 1)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        sessions.get(cookie)
    assert error.value.status_code == 401


def test_https_cookie_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOTSPLIT_SECURE_COOKIE", "true")
    with TestClient(
        create_app(tmp_path / "secure.db", TOKEN), base_url="https://testserver"
    ) as browser:
        response = browser.post("/api/auth/login", json={"token": TOKEN})
        assert "; Secure" in response.headers["set-cookie"]
        assert browser.get("/api/accounts").status_code == 200


def test_login_rotates_session_and_process_restart_invalidates_it(browser):
    browser.post("/api/auth/login", json={"token": TOKEN})
    first = browser.cookies.get(COOKIE)
    browser.post("/api/auth/login", json={"token": TOKEN})
    assert browser.cookies.get(COOKIE) != first
    browser.cookies.set(COOKIE, first)
    assert browser.get("/api/accounts").status_code == 401
