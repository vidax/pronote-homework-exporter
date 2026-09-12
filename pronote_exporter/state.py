from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Snapshot:
    payload: bytes
    etag: str
    generated_at: str

    @classmethod
    def from_bytes(cls, payload: bytes) -> "Snapshot":
        parsed = json.loads(payload)
        if not isinstance(parsed, dict) or parsed.get("schema_version") != 1:
            raise ValueError("Unsupported homework snapshot schema")
        generated_at = parsed.get("generated_at")
        if not isinstance(generated_at, str):
            raise ValueError("Snapshot has no generated_at timestamp")
        digest = parsed.get("content_hash")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("Snapshot has no valid content_hash")
        return cls(payload=payload, etag=f'"{digest}"', generated_at=generated_at)


class RuntimeState:
    def __init__(self, snapshot_path: Path):
        self._lock = threading.Lock()
        self._snapshot: Snapshot | None = None
        self._last_attempt_at: str | None = None
        self._last_success_at: str | None = None
        self._last_error: str | None = None
        self._mqtt_error: str | None = None
        self._refreshing = False

        try:
            self._snapshot = Snapshot.from_bytes(snapshot_path.read_bytes())
            self._last_success_at = self._snapshot.generated_at
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    @staticmethod
    def _now() -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

    def begin_refresh(self) -> bool:
        with self._lock:
            if self._refreshing:
                return False
            self._refreshing = True
            self._last_attempt_at = self._now()
            return True

    def finish_success(self, snapshot: Snapshot, mqtt_error: str | None = None) -> None:
        with self._lock:
            self._snapshot = snapshot
            self._last_success_at = snapshot.generated_at
            self._last_error = None
            self._mqtt_error = mqtt_error
            self._refreshing = False

    def finish_error(self, error: BaseException) -> None:
        with self._lock:
            self._last_error = f"{type(error).__name__}: {error}"
            self._refreshing = False

    def snapshot(self) -> Snapshot | None:
        with self._lock:
            return self._snapshot

    def health(self) -> dict[str, object]:
        with self._lock:
            return {
                "status": "ok" if self._snapshot and not self._last_error else "degraded",
                "snapshot_available": self._snapshot is not None,
                "refreshing": self._refreshing,
                "last_attempt_at": self._last_attempt_at,
                "last_success_at": self._last_success_at,
            }

    def diagnostic(self) -> dict[str, object]:
        with self._lock:
            return {
                **self._health_unlocked(),
                "last_error": self._last_error,
                "mqtt_error": self._mqtt_error,
            }

    def _health_unlocked(self) -> dict[str, object]:
        return {
            "status": "ok" if self._snapshot and not self._last_error else "degraded",
            "snapshot_available": self._snapshot is not None,
            "refreshing": self._refreshing,
            "last_attempt_at": self._last_attempt_at,
            "last_success_at": self._last_success_at,
        }
