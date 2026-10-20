"""Adaptateur isolé : seules trois opérations de lecture sont accessibles au worker."""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from lootsplit.connectors import ConnectorAccount
from lootsplit.domain import BankTransaction, BusinessError

MESSAGES = {
    "configuration": "Configurez la caisse régionale et les identifiants bancaires sur le serveur.",
    "module": "Le module Crédit Agricole n'est pas installé. Reconstruisez l'image Docker.",
    "credentials": "La banque a refusé les identifiants. Vérifiez la configuration du serveur.",
    "action_required": "La banque demande une validation. Connectez-vous à son site ou à son "
    "application, effectuez la validation demandée, puis réessayez ici.",
    "unavailable": "La banque ou son connecteur est indisponible. "
    "Réessayez plus tard ou utilisez le CSV.",
    "timeout": "La connexion bancaire a dépassé le délai autorisé. "
    "Aucune opération n'a été importée.",
    "account": "Le Livret A sélectionné n'est plus disponible. Vérifiez votre accès bancaire.",
    "data": "Le connecteur a renvoyé des données incomplètes. L'import a été annulé.",
}


class ConnectorError(BusinessError):
    def __init__(self, code: str):
        self.code = code if code in MESSAGES else "unavailable"
        super().__init__(MESSAGES[self.code])


def secret(name: str) -> str:
    filename = os.getenv(name + "_FILE")
    if filename:
        try:
            return Path(filename).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return os.getenv(name, "").strip()


@dataclass(frozen=True)
class BankConfiguration:
    website: str = ""
    login: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    modules_path: Path = Path("bank_modules")

    @classmethod
    def from_environment(cls):
        return cls(
            website=os.getenv("LOOTSPLIT_BANK_WEBSITE", "").strip(),
            login=secret("LOOTSPLIT_BANK_LOGIN"),
            password=secret("LOOTSPLIT_BANK_PASSWORD"),
            modules_path=Path(os.getenv("LOOTSPLIT_BANK_MODULES_PATH", "bank_modules")),
        )

    @property
    def credentials_configured(self):
        return bool(self.website and self.login and self.password)

    @property
    def module_installed(self):
        return (self.modules_path / "cragr" / "module.py").is_file()


class WoobConnector:
    source = "woob"

    def __init__(self, configuration: BankConfiguration, since: date | None = None):
        self.configuration = configuration
        self.since = since
        self._snapshot = None
        self._snapshot_account_id = None

    def _call(self, operation: str, **arguments):
        config = self.configuration
        if not config.credentials_configured:
            raise ConnectorError("configuration")
        if not config.module_installed:
            raise ConnectorError("module")
        payload = {
            "operation": operation,
            "website": config.website,
            "login": config.login,
            "password": config.password,
            "modules_path": str(config.modules_path.resolve()),
            **arguments,
        }
        try:
            # Secrets sur stdin, jamais dans les arguments ni les sorties de commande.
            result = subprocess.run(
                [sys.executable, "-m", "lootsplit.woob_worker"],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            response = json.loads(result.stdout)
            if result.returncode != 0 or not response.get("ok"):
                raise ConnectorError(response.get("error", "unavailable"))
            return response["data"]
        except subprocess.TimeoutExpired:
            raise ConnectorError("timeout") from None
        except (OSError, ValueError, KeyError):
            raise ConnectorError("unavailable") from None

    def discover(self) -> list[dict]:
        return self._call("accounts")

    def get_accounts(self) -> list[ConnectorAccount]:
        return [ConnectorAccount(item["id"], item["name"]) for item in self.discover()]

    def get_balance(self, account_id: str) -> int:
        if self.since is None:
            raise ConnectorError("data")
        self._snapshot = self._call("snapshot", account_id=account_id, since=self.since.isoformat())
        self._snapshot_account_id = account_id
        return self._snapshot["balance_cents"]

    def get_transactions(self, account_id: str, since: date) -> list[BankTransaction]:
        if self._snapshot is None or self._snapshot_account_id != account_id or since != self.since:
            raise ConnectorError("data")
        return [
            BankTransaction(
                booking_date=date.fromisoformat(t["booking_date"]),
                value_date=date.fromisoformat(t["value_date"]) if t["value_date"] else None,
                amount_cents=t["amount_cents"],
                raw_label=t["raw_label"],
                provider_transaction_id=t["provider_transaction_id"],
            )
            for t in self._snapshot["transactions"]
        ]
