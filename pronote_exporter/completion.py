from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import refresh_snapshot_metadata
from .storage import atomic_write_json

LOGGER = logging.getLogger(__name__)
MAX_EVENTS = 100
LOCAL_ID_PREFIX = "local-"


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _normalized_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def homework_identity(homework: dict[str, object]) -> dict[str, object]:
    return {
        "due": str(homework.get("due", "")),
        "subject": _normalized_text(homework.get("subject")),
        "description": _normalized_text(homework.get("description")),
    }


def homework_local_id(homework: dict[str, object]) -> str:
    canonical = json.dumps(
        homework_identity(homework),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return LOCAL_ID_PREFIX + hashlib.sha256(canonical).hexdigest()


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
            loaded_states = {
                str(key): value
                for key, value in states.items()
                if isinstance(value, dict) and isinstance(value.get("done"), bool)
            }
            self._events = [event for event in events if isinstance(event, dict)][
                -MAX_EVENTS:
            ]
            self._states, migrated = self._migrate_states(loaded_states)
            if migrated:
                self._save_unlocked()
        except FileNotFoundError:
            return
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            LOGGER.warning("Ignoring unreadable completion store %s: %s", self.path, exc)

    def _migrate_states(
        self, states: dict[str, dict[str, object]]
    ) -> tuple[dict[str, dict[str, object]], bool]:
        """Convert V1.1's volatile Pronote-ID keys to stable local keys."""
        event_homework: dict[str, dict[str, object]] = {}
        for event in self._events:
            homework = event.get("homework")
            if isinstance(homework, dict) and homework.get("id"):
                event_homework[str(homework["id"])] = homework

        result: dict[str, dict[str, object]] = {}
        migrated = False
        for saved_key, saved in states.items():
            identity = saved.get("identity")
            source = identity if isinstance(identity, dict) else event_homework.get(saved_key)
            if saved_key.startswith(LOCAL_ID_PREFIX):
                stable_key = saved_key
            elif source is not None:
                stable_key = homework_local_id(source)
                migrated = True
            else:
                # Keep an unmatched legacy key; it can still match until the
                # next Pronote refresh and does not affect new assignments.
                stable_key = saved_key

            normalized_saved = {
                "done": bool(saved["done"]),
                "updated_at": saved.get("updated_at"),
            }
            if source is not None:
                normalized_saved["identity"] = homework_identity(source)
            previous = result.get(stable_key)
            if previous is None or str(normalized_saved.get("updated_at") or "") >= str(
                previous.get("updated_at") or ""
            ):
                result[stable_key] = normalized_saved
        return result, migrated

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
            local_id = homework_local_id(homework)
            homework["local_id"] = local_id
            saved = states.get(local_id)
            if saved is None:
                # The student's planner status is deliberately independent
                # from Pronote: every unseen assignment starts as To do.
                homework["done"] = False
                homework["done_source"] = "default"
                homework.pop("done_updated_at", None)
                continue
            homework["done"] = bool(saved["done"])
            homework["done_source"] = "local"
            homework["done_updated_at"] = saved.get("updated_at")
        return refresh_snapshot_metadata(result)

    def set_done(
        self, homework: dict[str, object], done: bool
    ) -> dict[str, object] | None:
        local_id = homework_local_id(homework)
        occurred_at = _now()
        event: dict[str, object] | None = None

        with self._lock:
            self._states[local_id] = {
                "done": done,
                "updated_at": occurred_at,
                "identity": homework_identity(homework),
            }
            if done:
                event = {
                    "event_id": uuid.uuid4().hex,
                    "type": "homework.done",
                    "occurred_at": occurred_at,
                    "homework": {
                        "id": homework.get("id"),
                        "local_id": local_id,
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
