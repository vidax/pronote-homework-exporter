from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from pronote_exporter.models import build_snapshot
from pronote_exporter.service import HomeworkService
from pronote_exporter.state import RuntimeState
from tests.helpers import settings


class FakeSource:
    def fetch(self, date_from: date, date_to: date) -> dict[str, object]:
        student = SimpleNamespace(
            name="DUPONT Léo", class_name="5E A", establishment="Collège"
        )
        return build_snapshot([], student, date_from, date_to)


class BrokenPublisher:
    topic = "pronote/homework"

    def publish(self, payload: bytes) -> None:
        raise ConnectionError("broker unavailable")


class ServiceTests(unittest.TestCase):
    def test_mqtt_failure_does_not_invalidate_http_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "homework.json")
            configured = settings(output)
            state = RuntimeState(output)
            service = HomeworkService(
                configured,
                state,
                source=FakeSource(),  # type: ignore[arg-type]
                publisher=BrokenPublisher(),  # type: ignore[arg-type]
            )

            self.assertTrue(service.refresh(raise_errors=True))
            self.assertTrue(output.is_file())
            self.assertIsNotNone(state.snapshot())
            self.assertEqual(state.health()["status"], "ok")
            self.assertIn("ConnectionError", state.diagnostic()["mqtt_error"])
            self.assertEqual(json.loads(output.read_bytes())["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()

