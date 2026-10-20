"""Sessions locales en mémoire ; aucun secret administrateur conservé dans le navigateur."""

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

COOKIE = "lootsplit_session"
SESSION_SECONDS = 8 * 60 * 60


@dataclass(frozen=True)
class Session:
    csrf_token: str
    expires_at: float


class Sessions:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def login(self, address: str, supplied: str, expected: str) -> tuple[str, Session]:
        now = time.monotonic()
        with self._lock:
            self._attempts = {
                ip: [stamp for stamp in stamps if stamp > now - 60]
                for ip, stamps in self._attempts.items()
                if stamps and stamps[-1] > now - 60
            }
            attempts = self._attempts.setdefault(address, [])
            if len(attempts) >= 10 or sum(map(len, self._attempts.values())) >= 1000:
                raise HTTPException(429, "Trop de tentatives. Réessayez dans une minute.")
            attempts.append(now)
            if not secrets.compare_digest(supplied.encode(), expected.encode()):
                raise HTTPException(401, "Clé d'accès incorrecte.")
            self._sessions = {key: s for key, s in self._sessions.items() if s.expires_at > now}
            if len(self._sessions) >= 1000:
                raise HTTPException(429, "Trop de sessions actives.")
            token = secrets.token_urlsafe(48)
            session = Session(secrets.token_urlsafe(32), now + SESSION_SECONDS)
            self._sessions[self.key(token)] = session
            return token, session

    def get(self, token: str) -> Session:
        with self._lock:
            session = self._sessions.get(self.key(token))
            if session is None or session.expires_at <= time.monotonic():
                self._sessions.pop(self.key(token), None)
                raise HTTPException(401, "Votre session a expiré. Reconnectez-vous.")
            return session

    def logout(self, token: str):
        with self._lock:
            self._sessions.pop(self.key(token), None)


def session_from_request(request: Request, *, write: bool = False) -> Session:
    session = request.app.state.sessions.get(request.cookies.get(COOKIE, ""))
    if write and not secrets.compare_digest(
        request.headers.get("X-CSRF-Token", "").encode(), session.csrf_token.encode()
    ):
        raise HTTPException(403, "La validation de session a échoué. Rechargez la page.")
    return session


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=1000)


router = APIRouter(prefix="/api/auth", tags=["Session"])


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    address = request.client.host if request.client else "local"
    token, session = request.app.state.sessions.login(
        address, body.token, request.app.state.admin_token
    )
    request.app.state.sessions.logout(request.cookies.get(COOKIE, ""))
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=request.app.state.secure_cookie,
        samesite="strict",
        max_age=SESSION_SECONDS,
        path="/",
    )
    return {"actor": "ADMIN", "csrf_token": session.csrf_token}


@router.get("/session")
def current_session(request: Request):
    session = session_from_request(request)
    return {"actor": "ADMIN", "csrf_token": session.csrf_token}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    session_from_request(request, write=True)
    request.app.state.sessions.logout(request.cookies.get(COOKIE, ""))
    response.delete_cookie(
        COOKIE, path="/", secure=request.app.state.secure_cookie, httponly=True, samesite="strict"
    )
