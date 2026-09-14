from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta

from .completion import CompletionStore, EventFeed
from .config import Settings
from .models import encode_snapshot
from .mqtt import MqttPublisher
from .source import PronoteSource
from .state import RuntimeState, Snapshot
from .storage import atomic_write

LOGGER = logging.getLogger(__name__)


class HomeworkService:
    def __init__(
        self,
        settings: Settings,
        state: RuntimeState,
        source: PronoteSource | None = None,
        publisher: MqttPublisher | None = None,
        completion_store: CompletionStore | None = None,
    ):
        self.settings = settings
        self.state = state
        self.source = source or PronoteSource(settings)
        self.publisher = (
            publisher
            if publisher is not None
            else MqttPublisher.from_settings(settings)
        )
        self.completion_store = completion_store or CompletionStore(
            settings.completion_path
        )
        self._mutation_lock = threading.Lock()

    def refresh(self, *, raise_errors: bool = False) -> bool:
        if not self.state.begin_refresh():
            LOGGER.info("A refresh is already running")
            return False

        try:
            today = datetime.now(self.settings.timezone).date()
            date_from = today - timedelta(days=self.settings.days_past)
            date_to = today + timedelta(days=self.settings.days_ahead)
            fetched = self.source.fetch(date_from, date_to)
            with self._mutation_lock:
                document = self.completion_store.apply(fetched)
                payload = encode_snapshot(document)
                atomic_write(self.settings.output_path, payload, mode=0o600)
                snapshot = Snapshot.from_bytes(payload)
                self.state.finish_success(snapshot)
                mqtt_error = None
                if self.publisher is not None:
                    try:
                        self.publisher.publish(payload)
                        LOGGER.info(
                            "Published retained snapshot to MQTT topic %s",
                            self.publisher.topic,
                        )
                    except Exception as exc:  # MQTT must not invalidate HTTP.
                        mqtt_error = f"{type(exc).__name__}: {exc}"
                        LOGGER.warning("MQTT publish failed: %s", mqtt_error)
                self.state.set_mqtt_error(mqtt_error)
            LOGGER.info(
                "Homework snapshot refreshed (%d bytes, ETag %s)",
                len(payload),
                snapshot.etag,
            )
            return True
        except Exception as exc:
            self.state.finish_error(exc)
            LOGGER.exception("Homework refresh failed")
            if raise_errors:
                raise
            return False

    def set_homework_done(
        self, homework_id: str, done: bool
    ) -> dict[str, object]:
        """Persist a local completion override and update the live snapshot."""
        with self._mutation_lock:
            snapshot = self.state.snapshot()
            if snapshot is None:
                raise RuntimeError("Homework snapshot is not ready")
            document = json.loads(snapshot.payload)
            assignments = document.get("homework", [])
            homework = next(
                (
                    item
                    for item in assignments
                    if isinstance(item, dict) and str(item.get("id", "")) == homework_id
                ),
                None,
            )
            if homework is None:
                raise LookupError("Homework was not found")

            event = None
            changed = bool(homework.get("done")) != done
            if changed:
                event = self.completion_store.set_done(homework, done)
                document = self.completion_store.apply(document)
                payload = encode_snapshot(document)
                atomic_write(self.settings.output_path, payload, mode=0o600)
                self.state.replace_snapshot(Snapshot.from_bytes(payload))

                if self.publisher is not None:
                    try:
                        self.publisher.publish(payload)
                        if event is not None:
                            self.publisher.publish_event(
                                (json.dumps(event, ensure_ascii=False) + "\n").encode(
                                    "utf-8"
                                )
                            )
                        self.state.set_mqtt_error(None)
                    except Exception as exc:
                        mqtt_error = f"{type(exc).__name__}: {exc}"
                        self.state.set_mqtt_error(mqtt_error)
                        LOGGER.warning("MQTT status notification failed: %s", mqtt_error)

            updated = next(
                item
                for item in document["homework"]
                if str(item.get("id", "")) == homework_id
            )
            return {"homework": updated, "event": event}

    def completion_events(self) -> EventFeed:
        return self.completion_store.event_feed()

    def run_scheduler(self, stop_event: threading.Event) -> None:
        self.refresh()
        while not stop_event.wait(self.settings.refresh_interval):
            self.refresh()
