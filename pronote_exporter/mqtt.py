from __future__ import annotations

from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class MqttPublisher:
    host: str
    port: int
    username: str
    password: str
    topic: str
    event_topic: str
    qos: int
    tls: bool

    @classmethod
    def from_settings(cls, settings: Settings) -> "MqttPublisher | None":
        if not settings.mqtt_host:
            return None
        return cls(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            username=settings.mqtt_username,
            password=settings.mqtt_password,
            topic=settings.mqtt_topic,
            event_topic=settings.mqtt_event_topic,
            qos=settings.mqtt_qos,
            tls=settings.mqtt_tls,
        )

    def publish(self, payload: bytes) -> None:
        self._publish(self.topic, payload, retain=True)

    def publish_event(self, payload: bytes) -> None:
        self._publish(self.event_topic, payload, retain=False)

    def _publish(self, topic: str, payload: bytes, *, retain: bool) -> None:
        from paho.mqtt.publish import single

        authentication = None
        if self.username:
            authentication = {
                "username": self.username,
                "password": self.password or None,
            }

        single(
            topic,
            payload=payload,
            qos=self.qos,
            retain=retain,
            hostname=self.host,
            port=self.port,
            auth=authentication,
            tls={} if self.tls else None,
        )
