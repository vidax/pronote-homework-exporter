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


class AssignedSource:
    def fetch(self, date_from: date, date_to: date) -> dict[str, object]:
        student = SimpleNamespace(
            name="DUPONT Léo", class_name="5E A", establishment="Collège"
        )
        assignment = SimpleNamespace(
            id="42",
            date=date_from,
            subject=SimpleNamespace(name="Maths"),
            description="Exercises 1–3",
            done=False,
            background_color="#123456",
            files=[],
        )
        return build_snapshot([assignment], student, date_from, date_to)


class BrokenPublisher:
    topic = "pronote/homework"

    def publish(self, payload: bytes) -> None:
        raise ConnectionError("broker unavailable")


class CollectingPublisher:
    topic = "pronote/homework"

    def __init__(self) -> None:
        self.snapshots: list[bytes] = []
        self.events: list[bytes] = []

    def publish(self, payload: bytes) -> None:
        self.snapshots.append(payload)

    def publish_event(self, payload: bytes) -> None:
        self.events.append(payload)


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

    def test_local_done_state_survives_pronote_refresh_and_publishes_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "homework.json")
            configured = settings(output)
            state = RuntimeState(output)
            publisher = CollectingPublisher()
            service = HomeworkService(
                configured,
                state,
                source=AssignedSource(),  # type: ignore[arg-type]
                publisher=publisher,  # type: ignore[arg-type]
            )

            self.assertTrue(service.refresh(raise_errors=True))
            changed = service.set_homework_done("42", True)
            self.assertTrue(changed["homework"]["done"])  # type: ignore[index]
            self.assertEqual(changed["event"]["type"], "homework.done")  # type: ignore[index]
            self.assertEqual(len(publisher.events), 1)
            self.assertTrue(configured.completion_path.is_file())

            self.assertTrue(service.refresh(raise_errors=True))
            current = json.loads(state.snapshot().payload)  # type: ignore[union-attr]
            self.assertTrue(current["homework"][0]["done"])
            self.assertEqual(current["homework"][0]["done_source"], "local")


if __name__ == "__main__":
    unittest.main()
