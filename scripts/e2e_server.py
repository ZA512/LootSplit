"""Serveur de test navigateur sur une base temporaire, sans toucher aux données locales."""

import os
import tempfile
from pathlib import Path

import uvicorn

from lootsplit.api import create_app

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="lootsplit-e2e-") as directory:
        app = create_app(Path(directory) / "app.db", os.environ["LOOTSPLIT_E2E_TOKEN"])
        uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
