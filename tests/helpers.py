from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from pronote_exporter.config import Settings


def settings(output_path: Path, **changes: object) -> Settings:
    values: dict[str, object] = {
        "pronote_url": "https://example.test/pronote/eleve.html",
        "pronote_username": "student",
        "pronote_password": "secret",
        "auth_mode": "password",
        "account_type": "student",
        "child_name": "",
        "ent_name": "",
        "account_pin": "",
        "credentials_path": output_path.parent / "credentials.json",
        "output_path": output_path,
        "completion_path": output_path.parent / "completions.json",
        "days_past": 0,
        "days_ahead": 21,
        "refresh_interval": 900,
        "timezone": ZoneInfo("Europe/Paris"),
        "http_host": "127.0.0.1",
        "http_port": 8080,
        "api_key": "",
        "mqtt_host": "",
        "mqtt_port": 1883,
        "mqtt_username": "",
        "mqtt_password": "",
        "mqtt_topic": "pronote/homework",
        "mqtt_event_topic": "pronote/homework/done",
        "mqtt_qos": 1,
        "mqtt_tls": False,
    }
    values.update(changes)
    return Settings(**values)  # type: ignore[arg-type]
