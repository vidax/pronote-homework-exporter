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
            qos=settings.mqtt_qos,
            tls=settings.mqtt_tls,
        )

    def publish(self, payload: bytes) -> None:
        from paho.mqtt.publish import single

        authentication = None
        if self.username:
            authentication = {
                "username": self.username,
                "password": self.password or None,
            }

        single(
            self.topic,
            payload=payload,
            qos=self.qos,
            retain=True,
            hostname=self.host,
            port=self.port,
            auth=authentication,
            tls={} if self.tls else None,
        )

