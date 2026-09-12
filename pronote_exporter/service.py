from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

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
    ):
        self.settings = settings
        self.state = state
        self.source = source or PronoteSource(settings)
        self.publisher = (
            publisher
            if publisher is not None
            else MqttPublisher.from_settings(settings)
        )

    def refresh(self, *, raise_errors: bool = False) -> bool:
        if not self.state.begin_refresh():
            LOGGER.info("A refresh is already running")
            return False

        try:
            today = datetime.now(self.settings.timezone).date()
            date_from = today - timedelta(days=self.settings.days_past)
            date_to = today + timedelta(days=self.settings.days_ahead)
            document = self.source.fetch(date_from, date_to)
            payload = encode_snapshot(document)

            atomic_write(self.settings.output_path, payload, mode=0o600)
            snapshot = Snapshot.from_bytes(payload)

            mqtt_error = None
            if self.publisher is not None:
                try:
                    self.publisher.publish(payload)
                    LOGGER.info(
                        "Published retained snapshot to MQTT topic %s",
                        self.publisher.topic,
                    )
                except Exception as exc:  # MQTT must not invalidate the HTTP cache.
                    mqtt_error = f"{type(exc).__name__}: {exc}"
                    LOGGER.warning("MQTT publish failed: %s", mqtt_error)

            self.state.finish_success(snapshot, mqtt_error=mqtt_error)
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

    def run_scheduler(self, stop_event: threading.Event) -> None:
        self.refresh()
        while not stop_event.wait(self.settings.refresh_interval):
            self.refresh()

