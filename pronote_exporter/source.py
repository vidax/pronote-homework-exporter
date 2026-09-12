from __future__ import annotations

import json
import logging
import secrets
from datetime import date
from pathlib import Path
from typing import Any

from .config import ConfigError, Settings
from .models import build_snapshot
from .storage import atomic_write_json

LOGGER = logging.getLogger(__name__)


class PronoteSource:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _load_library(self) -> Any:
        try:
            import pronotepy
        except ImportError as exc:
            raise RuntimeError(
                "pronotepy is not installed; install the project dependencies"
            ) from exc
        return pronotepy

    def _account_class(self, pronotepy: Any, url: str) -> Any:
        account_type = self.settings.account_type
        if account_type == "auto":
            account_type = "parent" if "parent.html" in url else "student"
        return pronotepy.ParentClient if account_type == "parent" else pronotepy.Client

    def _ent_function(self, pronotepy: Any) -> Any | None:
        if not self.settings.ent_name:
            return None
        function = getattr(pronotepy.ent, self.settings.ent_name, None)
        if not callable(function):
            raise ConfigError(
                f"Unknown PRONOTE_ENT function: {self.settings.ent_name}"
            )
        return function

    def _direct_client(self, pronotepy: Any) -> Any:
        client_class = self._account_class(pronotepy, self.settings.pronote_url)
        kwargs: dict[str, object] = {"device_name": "Homework e-ink exporter"}
        if self.settings.account_pin:
            kwargs["account_pin"] = self.settings.account_pin
        return client_class(
            self.settings.pronote_url,
            self.settings.pronote_username,
            self.settings.pronote_password,
            ent=self._ent_function(pronotepy),
            **kwargs,
        )

    def _token_client(self, pronotepy: Any) -> Any:
        path = self.settings.credentials_path
        try:
            credentials = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Cannot load token credentials from {path}: {exc}") from exc
        if not isinstance(credentials, dict):
            raise ConfigError(f"Token credentials at {path} must contain a JSON object")
        required_keys = {
            "pronote_url",
            "username",
            "password",
            "uuid",
            "client_identifier",
        }
        missing = required_keys.difference(credentials)
        if missing:
            raise ConfigError(
                f"Token credentials at {path} are missing: {', '.join(sorted(missing))}"
            )
        credentials = {key: credentials[key] for key in required_keys}

        credential_url = str(credentials.get("pronote_url", ""))
        client_class = self._account_class(
            pronotepy, credential_url or self.settings.pronote_url
        )
        kwargs: dict[str, object] = {"device_name": "Homework e-ink exporter"}
        if self.settings.account_pin:
            kwargs["account_pin"] = self.settings.account_pin
        client = client_class.token_login(**credentials, **kwargs)
        if not client.logged_in:
            raise RuntimeError("Pronote rejected the token login")

        # Pronote rotates the mobile token at every login. Persisting the new
        # credentials before doing more work avoids losing the usable token.
        atomic_write_json(path, client.export_credentials(), mode=0o600)
        return client

    def _connect(self, pronotepy: Any) -> Any:
        if self.settings.auth_mode == "token":
            client = self._token_client(pronotepy)
        else:
            client = self._direct_client(pronotepy)
        if hasattr(client, "account_pin"):
            del client.account_pin
        return client

    def fetch(self, date_from: date, date_to: date) -> dict[str, object]:
        pronotepy = self._load_library()
        client = None
        try:
            client = self._connect(pronotepy)
            if not client.logged_in:
                raise RuntimeError("Pronote rejected the login")

            if isinstance(client, pronotepy.ParentClient):
                if self.settings.child_name:
                    available = [child.name for child in client.children]
                    if self.settings.child_name not in available:
                        raise ConfigError(
                            "PRONOTE_CHILD_NAME was not found. Available children: "
                            + ", ".join(available)
                        )
                    client.set_child(self.settings.child_name)
                student = client._selected_child
                LOGGER.info("Fetching homework for child %s", student.name)
            else:
                student = client.info
                LOGGER.info("Fetching homework for student %s", student.name)

            assignments = client.homework(date_from, date_to)
            return build_snapshot(assignments, student, date_from, date_to)
        finally:
            if client is not None:
                session = getattr(getattr(client, "communication", None), "session", None)
                if session is not None:
                    session.close()

    def create_token_credentials(self) -> Path:
        if self.settings.auth_mode != "password":
            raise ConfigError(
                "Set PRONOTE_AUTH_MODE=password while creating initial token credentials"
            )

        pronotepy = self._load_library()
        direct_client = None
        token_client = None
        try:
            direct_client = self._direct_client(pronotepy)
            if not direct_client.logged_in:
                raise RuntimeError("Pronote rejected the login")

            pin = "".join(secrets.choice("123456789") for _ in range(4))
            qr_data = direct_client.request_qr_code_data(pin)
            uuid = secrets.token_hex(16)
            client_class = type(direct_client)

            kwargs: dict[str, object] = {
                "device_name": "Homework e-ink exporter"
            }
            if self.settings.account_pin:
                kwargs["account_pin"] = self.settings.account_pin
            token_client = client_class.qrcode_login(qr_data, pin, uuid, **kwargs)
            atomic_write_json(
                self.settings.credentials_path,
                token_client.export_credentials(),
                mode=0o600,
            )
            return self.settings.credentials_path
        finally:
            for client in (token_client, direct_client):
                if client is None:
                    continue
                session = getattr(
                    getattr(client, "communication", None), "session", None
                )
                if session is not None:
                    session.close()
