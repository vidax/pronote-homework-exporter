from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import refresh_snapshot_metadata
from .storage import atomic_write_json

LOGGER = logging.getLogger(__name__)
MAX_EVENTS = 100


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class EventFeed:
    payload: bytes
    etag: str


class CompletionStore:
    """Persistent local completion overrides and recent done events."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._states: dict[str, dict[str, object]] = {}
        self._events: list[dict[str, object]] = []
        self._load()

    def _load(self) -> None:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            states = document.get("states", {})
            events = document.get("events", [])
            if not isinstance(states, dict) or not isinstance(events, list):
                raise ValueError("invalid completion store structure")
            self._states = {
                str(key): value
                for key, value in states.items()
                if isinstance(value, dict) and isinstance(value.get("done"), bool)
            }
            self._events = [event for event in events if isinstance(event, dict)][
                -MAX_EVENTS:
            ]
        except FileNotFoundError:
            return
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            LOGGER.warning("Ignoring unreadable completion store %s: %s", self.path, exc)

    def _save_unlocked(self) -> None:
        atomic_write_json(
            self.path,
            {
                "schema_version": 1,
                "states": self._states,
                "events": self._events,
            },
            mode=0o600,
        )

    def apply(self, snapshot: dict[str, object]) -> dict[str, object]:
        result = copy.deepcopy(snapshot)
        assignments = result.get("homework", [])
        if not isinstance(assignments, list):
            raise ValueError("Snapshot homework must be an array")

        with self._lock:
            states = copy.deepcopy(self._states)
        for homework in assignments:
            if not isinstance(homework, dict):
                continue
            saved = states.get(str(homework.get("id", "")))
            if saved is None:
                homework["done_source"] = "pronote"
                continue
            homework["done"] = bool(saved["done"])
            homework["done_source"] = "local"
            homework["done_updated_at"] = saved.get("updated_at")
        return refresh_snapshot_metadata(result)

    def set_done(
        self, homework: dict[str, object], done: bool
    ) -> dict[str, object] | None:
        homework_id = str(homework.get("id", ""))
        if not homework_id:
            raise ValueError("Homework has no id")
        occurred_at = _now()
        event: dict[str, object] | None = None

        with self._lock:
            self._states[homework_id] = {
                "done": done,
                "updated_at": occurred_at,
            }
            if done:
                event = {
                    "event_id": uuid.uuid4().hex,
                    "type": "homework.done",
                    "occurred_at": occurred_at,
                    "homework": {
                        "id": homework_id,
                        "due": homework.get("due"),
                        "subject": homework.get("subject"),
                        "description": homework.get("description"),
                    },
                }
                self._events.append(event)
                self._events = self._events[-MAX_EVENTS:]
            self._save_unlocked()
        return copy.deepcopy(event)

    def event_feed(self) -> EventFeed:
        with self._lock:
            events = copy.deepcopy(self._events)
        document = {
            "schema_version": 1,
            "latest_event_id": events[-1].get("event_id") if events else None,
            "events": events,
        }
        payload = (
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        return EventFeed(payload=payload, etag=f'"{hashlib.sha256(payload).hexdigest()}"')
