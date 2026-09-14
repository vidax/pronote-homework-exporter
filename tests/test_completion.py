from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pronote_exporter.completion import CompletionStore


def snapshot(done: bool = False, homework_id: str = "42") -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": "2026-09-14T08:00:00Z",
        "range": {"from": "2026-09-14", "to": "2026-10-05"},
        "student": {"name": "Léo", "class": "5E", "establishment": "School"},
        "homework": [
            {
                "id": homework_id,
                "due": "2026-09-15",
                "subject": "Maths",
                "description": "Exercises 1–3",
                "done": done,
                "color": "#123456",
                "attachments": [],
            }
        ],
    }


class CompletionStoreTests(unittest.TestCase):
    def test_status_survives_reload_and_overrides_pronote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "completions.json")
            store = CompletionStore(path)
            homework = snapshot()["homework"][0]  # type: ignore[index]

            event = store.set_done(homework, True)  # type: ignore[arg-type]
            self.assertEqual(event["type"], "homework.done")  # type: ignore[index]

            reloaded = CompletionStore(path)
            applied = reloaded.apply(snapshot(done=False))
            result = applied["homework"][0]  # type: ignore[index]
            self.assertTrue(result["done"])
            self.assertEqual(result["done_source"], "local")
            self.assertEqual(applied["summary"]["done"], 1)  # type: ignore[index]

            feed = json.loads(reloaded.event_feed().payload)
            self.assertEqual(feed["latest_event_id"], event["event_id"])  # type: ignore[index]
            self.assertEqual(len(feed["events"]), 1)

    def test_unchecking_persists_without_creating_done_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CompletionStore(Path(directory, "completions.json"))
            homework = snapshot(done=True)["homework"][0]  # type: ignore[index]

            self.assertIsNone(store.set_done(homework, False))  # type: ignore[arg-type]
            self.assertFalse(store.apply(snapshot(done=True))["homework"][0]["done"])  # type: ignore[index]
            self.assertEqual(json.loads(store.event_feed().payload)["events"], [])

    def test_volatile_pronote_id_does_not_change_local_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CompletionStore(Path(directory, "completions.json"))
            original = store.apply(snapshot(homework_id="old-pronote-id"))
            homework = original["homework"][0]  # type: ignore[index]
            local_id = homework["local_id"]
            store.set_done(homework, True)  # type: ignore[arg-type]

            refreshed = store.apply(snapshot(homework_id="new-pronote-id"))
            result = refreshed["homework"][0]  # type: ignore[index]
            self.assertEqual(result["local_id"], local_id)
            self.assertTrue(result["done"])
            self.assertEqual(result["done_source"], "local")

    def test_unseen_homework_defaults_to_todo_even_if_pronote_says_done(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CompletionStore(Path(directory, "completions.json"))
            result = store.apply(snapshot(done=True))["homework"][0]  # type: ignore[index]
            self.assertFalse(result["done"])
            self.assertEqual(result["done_source"], "default")

    def test_v110_store_is_migrated_using_event_homework_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "completions.json")
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "states": {
                            "old-pronote-id": {
                                "done": True,
                                "updated_at": "2026-09-14T08:00:00Z",
                            }
                        },
                        "events": [
                            {
                                "event_id": "event-1",
                                "type": "homework.done",
                                "occurred_at": "2026-09-14T08:00:00Z",
                                "homework": {
                                    "id": "old-pronote-id",
                                    "due": "2026-09-15",
                                    "subject": "Maths",
                                    "description": "Exercises 1–3",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            store = CompletionStore(path)
            result = store.apply(snapshot(homework_id="new-pronote-id"))["homework"][0]  # type: ignore[index]
            self.assertTrue(result["done"])
            saved = json.loads(path.read_text(encoding="utf-8"))["states"]
            self.assertTrue(all(key.startswith("local-") for key in saved))


if __name__ == "__main__":
    unittest.main()
