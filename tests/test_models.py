from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from pronote_exporter.models import build_snapshot, encode_snapshot


class ModelsTests(unittest.TestCase):
    def test_builds_sorted_stable_contract(self) -> None:
        link = SimpleNamespace(type=0, name="Consigne", url="https://example.test")
        homework = [
            SimpleNamespace(
                id="2",
                date=date(2026, 9, 10),
                subject=SimpleNamespace(name=" Maths "),
                description="Exercice\n  2",
                done=True,
                background_color="ABCDEF",
                files=[],
            ),
            SimpleNamespace(
                id="1",
                date=date(2026, 9, 9),
                subject=SimpleNamespace(name="Français"),
                description="Lire   le texte",
                done=False,
                background_color="#123456",
                files=[link],
            ),
        ]
        student = SimpleNamespace(
            name="DUPONT Léo", class_name="5E A", establishment="Collège"
        )

        snapshot = build_snapshot(
            homework,
            student,
            date(2026, 9, 7),
            date(2026, 9, 28),
            datetime(2026, 9, 7, 14, tzinfo=timezone.utc),
        )

        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["summary"]["pending"], 2)  # type: ignore[index]
        self.assertEqual(snapshot["summary"]["next_due"], "2026-09-09")  # type: ignore[index]
        self.assertEqual(snapshot["homework"][0]["id"], "1")  # type: ignore[index]
        self.assertEqual(
            snapshot["homework"][0]["description"], "Lire le texte"  # type: ignore[index]
        )
        self.assertEqual(snapshot["homework"][1]["color"], "#ABCDEF")  # type: ignore[index]
        self.assertFalse(snapshot["homework"][1]["done"])  # type: ignore[index]
        self.assertTrue(encode_snapshot(snapshot).endswith(b"\n"))

    def test_content_hash_ignores_fetch_time(self) -> None:
        student = SimpleNamespace(name="Léo", class_name="5E", establishment="School")
        first = build_snapshot(
            [],
            student,
            date(2026, 9, 7),
            date(2026, 9, 28),
            datetime(2026, 9, 7, 14, tzinfo=timezone.utc),
        )
        second = build_snapshot(
            [],
            student,
            date(2026, 9, 8),
            date(2026, 9, 29),
            datetime(2026, 9, 8, 14, tzinfo=timezone.utc),
        )
        self.assertNotEqual(first["generated_at"], second["generated_at"])
        self.assertEqual(first["content_hash"], second["content_hash"])



if __name__ == "__main__":
    unittest.main()
