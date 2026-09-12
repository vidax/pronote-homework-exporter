from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(ValueError):
    """Raised when environment configuration is invalid."""


def _value(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _secret(name: str) -> str:
    direct = os.environ.get(name)
    file_name = os.environ.get(f"{name}_FILE")
    if direct is not None and file_name:
        raise ConfigError(f"Set only one of {name} and {name}_FILE")
    if file_name:
        try:
            return Path(file_name).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError(f"Cannot read {name}_FILE: {exc}") from exc
    return (direct or "").strip()


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = _value(name, str(default))
    try:
        result = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if not minimum <= result <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return result


def _boolean(name: str, default: bool = False) -> bool:
    raw = _value(name, "true" if default else "false").lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false")


@dataclass(frozen=True)
class Settings:
    pronote_url: str
    pronote_username: str
    pronote_password: str
    auth_mode: str
    account_type: str
    child_name: str
    ent_name: str
    account_pin: str
    credentials_path: Path
    output_path: Path
    days_past: int
    days_ahead: int
    refresh_interval: int
    timezone: ZoneInfo
    http_host: str
    http_port: int
    api_key: str
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    mqtt_topic: str
    mqtt_qos: int
    mqtt_tls: bool

    @classmethod
    def from_env(cls) -> "Settings":
        auth_mode = _value("PRONOTE_AUTH_MODE", "password").lower()
        if auth_mode not in {"password", "token"}:
            raise ConfigError("PRONOTE_AUTH_MODE must be password or token")

        account_type = _value("PRONOTE_ACCOUNT_TYPE", "auto").lower()
        if account_type not in {"auto", "student", "parent"}:
            raise ConfigError(
                "PRONOTE_ACCOUNT_TYPE must be auto, student, or parent"
            )

        pronote_url = _value("PRONOTE_URL")
        pronote_username = _secret("PRONOTE_USERNAME")
        pronote_password = _secret("PRONOTE_PASSWORD")
        credentials_path = Path(
            _value("PRONOTE_CREDENTIALS_PATH", "/data/credentials.json")
        )

        if auth_mode == "password":
            missing = [
                name
                for name, value in (
                    ("PRONOTE_URL", pronote_url),
                    ("PRONOTE_USERNAME", pronote_username),
                    ("PRONOTE_PASSWORD", pronote_password),
                )
                if not value
            ]
            if missing:
                raise ConfigError(f"Missing required setting(s): {', '.join(missing)}")
        elif not credentials_path.is_file():
            raise ConfigError(
                f"Token credentials not found at {credentials_path}. "
                "Run 'pronote-homework create-token' while using password auth first."
            )

        timezone_name = _value("TZ", "Europe/Paris")
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"Unknown TZ value: {timezone_name}") from exc

        mqtt_qos = _integer("MQTT_QOS", 1, 0, 2)
        api_key = _secret("API_KEY")
        if api_key == "replace-with-output-of-openssl-rand-hex-24":
            raise ConfigError("Replace the example API_KEY before starting the service")

        return cls(
            pronote_url=pronote_url,
            pronote_username=pronote_username,
            pronote_password=pronote_password,
            auth_mode=auth_mode,
            account_type=account_type,
            child_name=_value("PRONOTE_CHILD_NAME"),
            ent_name=_value("PRONOTE_ENT"),
            account_pin=_secret("PRONOTE_ACCOUNT_PIN"),
            credentials_path=credentials_path,
            output_path=Path(_value("OUTPUT_PATH", "/data/homework.json")),
            days_past=_integer("DAYS_PAST", 7, 0, 31),
            days_ahead=_integer("DAYS_AHEAD", 21, 1, 180),
            refresh_interval=_integer("REFRESH_INTERVAL", 900, 300, 86400),
            timezone=timezone,
            http_host=_value("HTTP_HOST", "0.0.0.0"),
            http_port=_integer("HTTP_PORT", 8080, 1, 65535),
            api_key=api_key,
            mqtt_host=_value("MQTT_HOST"),
            mqtt_port=_integer("MQTT_PORT", 1883, 1, 65535),
            mqtt_username=_value("MQTT_USERNAME"),
            mqtt_password=_secret("MQTT_PASSWORD"),
            mqtt_topic=_value("MQTT_TOPIC", "pronote/homework"),
            mqtt_qos=mqtt_qos,
            mqtt_tls=_boolean("MQTT_TLS", False),
        )
