from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pronote_exporter.config import ConfigError, Settings


class SettingsTests(unittest.TestCase):
    def test_password_settings(self) -> None:
        environment = {
            "PRONOTE_URL": "https://example.test/pronote/parent.html",
            "PRONOTE_USERNAME": "parent",
            "PRONOTE_PASSWORD": "password",
            "DAYS_AHEAD": "14",
            "MQTT_TLS": "true",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.account_type, "auto")
        self.assertEqual(settings.days_ahead, 14)
        self.assertTrue(settings.mqtt_tls)

    def test_secret_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            password_file = Path(directory, "password")
            password_file.write_text("from-file\n", encoding="utf-8")
            environment = {
                "PRONOTE_URL": "https://example.test/pronote/eleve.html",
                "PRONOTE_USERNAME": "student",
                "PRONOTE_PASSWORD_FILE": str(password_file),
            }
            with patch.dict(os.environ, environment, clear=True):
                settings = Settings.from_env()
        self.assertEqual(settings.pronote_password, "from-file")

    def test_refresh_interval_has_safe_minimum(self) -> None:
        environment = {
            "PRONOTE_URL": "https://example.test/pronote/eleve.html",
            "PRONOTE_USERNAME": "student",
            "PRONOTE_PASSWORD": "password",
            "REFRESH_INTERVAL": "60",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ConfigError, "REFRESH_INTERVAL"):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()

