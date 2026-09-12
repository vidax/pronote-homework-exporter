from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pronote_exporter.state import RuntimeState, Snapshot
from pronote_exporter.storage import atomic_write


PAYLOAD = (
    b'{"content_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
    b'"generated_at":"2026-09-07T14:00:00Z","schema_version":1}\n'
)


class StorageStateTests(unittest.TestCase):
    def test_atomic_write_and_cached_snapshot_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "homework.json")
            atomic_write(path, PAYLOAD)
            state = RuntimeState(path)

            self.assertEqual(state.snapshot().payload, PAYLOAD)  # type: ignore[union-attr]
            self.assertTrue(state.health()["snapshot_available"])

    def test_refresh_error_keeps_last_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = RuntimeState(Path(directory, "missing.json"))
            snapshot = Snapshot.from_bytes(PAYLOAD)
            self.assertTrue(state.begin_refresh())
            state.finish_success(snapshot)
            self.assertTrue(state.begin_refresh())
            state.finish_error(RuntimeError("temporary outage"))

            self.assertEqual(state.snapshot(), snapshot)
            self.assertEqual(state.health()["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
