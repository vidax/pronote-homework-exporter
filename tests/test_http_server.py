from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from pronote_exporter.completion import EventFeed
from pronote_exporter.http_server import HomeworkHTTPServer
from pronote_exporter.state import RuntimeState, Snapshot


PAYLOAD = (
    b'{"content_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
    b'"generated_at":"2026-09-07T14:00:00Z","schema_version":1}\n'
)


class HTTPServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        state = RuntimeState(Path(self.temporary.name, "missing.json"))
        state.begin_refresh()
        state.finish_success(Snapshot.from_bytes(PAYLOAD))
        self.completion_calls: list[tuple[str, bool]] = []

        def set_done(homework_id: str, done: bool) -> dict[str, object]:
            if homework_id != "42":
                raise LookupError(homework_id)
            self.completion_calls.append((homework_id, done))
            return {
                "homework": {"id": homework_id, "done": done},
                "event": {"type": "homework.done"} if done else None,
            }

        self.event_feed = EventFeed(
            payload=b'{"events":[],"latest_event_id":null,"schema_version":1}\n',
            etag='"event-etag"',
        )
        self.server = HomeworkHTTPServer(
            ("127.0.0.1", 0),
            state,
            "test-key",
            completion_handler=set_done,
            events_provider=lambda: self.event_feed,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request(
        self,
        path: str,
        headers: dict[str, str] | None = None,
        *,
        method: str = "GET",
        body: bytes | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        body = response.read()
        result = response.status, dict(response.getheaders()), body
        connection.close()
        return result

    def test_requires_api_key(self) -> None:
        status, _, _ = self.request("/homework.json")
        self.assertEqual(status, 401)

    def test_student_can_update_status_without_api_key(self) -> None:
        body = json.dumps({"done": True}).encode()
        status, _, response = self.request(
            "/planner/homework/42/done",
            {"Content-Type": "application/json"},
            method="POST",
            body=body,
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.completion_calls, [("42", True)])
        self.assertTrue(json.loads(response)["homework"]["done"])

        status, _, _ = self.request(
            "/planner/homework/42/done",
            {"Content-Type": "application/json"},
            method="POST",
            body=b'{"done":"yes"}',
        )
        self.assertEqual(status, 400)

        status, _, _ = self.request(
            "/planner/homework/42/done",
            {"Content-Type": "text/plain"},
            method="POST",
            body=b'{"done":true}',
        )
        self.assertEqual(status, 415)

    def test_event_feed_is_api_key_protected_and_supports_etag(self) -> None:
        status, _, _ = self.request("/v1/events")
        self.assertEqual(status, 401)

        status, headers, body = self.request(
            "/v1/events", {"X-API-Key": "test-key"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, self.event_feed.payload)
        self.assertEqual(headers["ETag"], self.event_feed.etag)

        status, _, body = self.request(
            "/v1/events",
            {"X-API-Key": "test-key", "If-None-Match": self.event_feed.etag},
        )
        self.assertEqual(status, 304)
        self.assertEqual(body, b"")

    def test_etag_conditional_request(self) -> None:
        status, headers, body = self.request(
            "/homework.json", {"X-API-Key": "test-key"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, PAYLOAD)

        status, _, body = self.request(
            "/homework.json",
            {"X-API-Key": "test-key", "If-None-Match": headers["ETag"]},
        )
        self.assertEqual(status, 304)
        self.assertEqual(body, b"")

    def test_health_is_public_and_minimal(self) -> None:
        status, _, body = self.request("/healthz")
        self.assertEqual(status, 200)
        self.assertNotIn(b"last_error", body)

    def test_web_planner_is_public_but_machine_api_remains_private(self) -> None:
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertIn(b"Monday to Friday", body)

        status, _, body = self.request("/assets/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b'/planner.json', body)
        self.assertIn(b'/planner/homework/', body)
        self.assertNotIn(b'X-API-Key', body)

        status, _, body = self.request("/planner.json")
        self.assertEqual(status, 200)
        self.assertEqual(body, PAYLOAD)

        status, _, _ = self.request("/homework.json")
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
