from __future__ import annotations

import hmac
import json
import logging
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any
from urllib.parse import urlsplit

from .state import RuntimeState

LOGGER = logging.getLogger(__name__)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")


WEB_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8", "no-cache"),
    "/index.html": ("index.html", "text/html; charset=utf-8", "no-cache"),
    "/assets/styles.css": ("styles.css", "text/css; charset=utf-8", "no-cache"),
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8", "no-cache"),
}


@lru_cache(maxsize=len(WEB_ASSETS))
def _web_asset(name: str) -> bytes:
    return files("pronote_exporter").joinpath("web", name).read_bytes()


class HomeworkHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        state: RuntimeState,
        api_key: str,
    ):
        self.state = state
        self.api_key = api_key
        super().__init__(address, HomeworkRequestHandler)


class HomeworkRequestHandler(BaseHTTPRequestHandler):
    server: HomeworkHTTPServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._handle(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        self._handle(send_body=False)

    def _authorized(self) -> bool:
        expected = self.server.api_key
        if not expected:
            return True
        supplied = self.headers.get("X-API-Key", "")
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            supplied = authorization[7:]
        return hmac.compare_digest(supplied, expected)

    def _handle(self, *, send_body: bool) -> None:
        path = urlsplit(self.path).path

        asset = WEB_ASSETS.get(path)
        if asset:
            name, content_type, cache_control = asset
            self._send(
                200,
                _web_asset(name),
                content_type,
                send_body=send_body,
                extra_headers={
                    "Cache-Control": cache_control,
                    "Content-Security-Policy": (
                        "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                        "script-src 'self'; style-src 'self'; object-src 'none'; "
                        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                    ),
                    "Referrer-Policy": "no-referrer",
                },
            )
            return

        if path == "/healthz":
            health = self.server.state.health()
            public_health = {
                "status": health["status"],
                "snapshot_available": health["snapshot_available"],
            }
            self._send_json(200, public_health, send_body=send_body)
            return

        if path not in {
            "/planner.json",
            "/homework.json",
            "/v1/homework",
            "/v1/status",
        }:
            self._send_json(404, {"error": "not_found"}, send_body=send_body)
            return

        # The browser planner is intentionally available to the trusted LAN.
        # Machine-facing JSON and diagnostics remain protected by the API key.
        if path != "/planner.json" and not self._authorized():
            self._send_json(
                401,
                {"error": "unauthorized"},
                send_body=send_body,
                extra_headers={"WWW-Authenticate": "Bearer"},
            )
            return

        if path == "/v1/status":
            self._send_json(200, self.server.state.diagnostic(), send_body=send_body)
            return

        snapshot = self.server.state.snapshot()
        if snapshot is None:
            self._send_json(
                503,
                {"error": "snapshot_not_ready"},
                send_body=send_body,
                extra_headers={"Retry-After": "60"},
            )
            return

        if self.headers.get("If-None-Match") == snapshot.etag:
            self.send_response(304)
            self.send_header("ETag", snapshot.etag)
            self.send_header("Cache-Control", "private, no-cache")
            self.end_headers()
            return

        self._send(
            200,
            snapshot.payload,
            "application/json; charset=utf-8",
            send_body=send_body,
            extra_headers={
                "ETag": snapshot.etag,
                "Cache-Control": "private, no-cache",
            },
        )

    def _send_json(
        self,
        status: int,
        value: object,
        *,
        send_body: bool,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._send(
            status,
            _json_bytes(value),
            "application/json; charset=utf-8",
            send_body=send_body,
            extra_headers=extra_headers,
        )

    def _send(
        self,
        status: int,
        payload: bytes,
        content_type: str,
        *,
        send_body: bool,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()
        if send_body:
            self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("HTTP %s - %s", self.client_address[0], format % args)
