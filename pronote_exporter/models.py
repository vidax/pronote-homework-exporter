from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Any, Iterable


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _attachment(item: Any) -> dict[str, object]:
    kind = "link" if getattr(item, "type", 1) == 0 else "file"
    return {
        "name": _text(getattr(item, "name", "")),
        "kind": kind,
        # Pronote file URLs are tied to a short-lived login session. Publishing
        # them in a cached snapshot would give clients a misleading dead URL.
        "url": getattr(item, "url", None) if kind == "link" else None,
    }


def _homework(item: Any) -> dict[str, object]:
    attachments: list[dict[str, object]] = []
    try:
        attachments = [_attachment(file) for file in item.files]
    except (AttributeError, KeyError, TypeError, ValueError):
        # A malformed attachment should not hide the homework itself.
        attachments = []

    color = _text(getattr(item, "background_color", "")) or None
    if color and not color.startswith("#"):
        color = f"#{color}"

    return {
        "id": str(getattr(item, "id", "")),
        "due": item.date.isoformat(),
        "subject": _text(getattr(getattr(item, "subject", None), "name", "")),
        "description": _text(getattr(item, "description", "")),
        "done": bool(getattr(item, "done", False)),
        "color": color,
        "attachments": attachments,
    }


def build_snapshot(
    homework: Iterable[Any],
    student: Any,
    date_from: date,
    date_to: date,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    generated_at = generated_at or datetime.now(timezone.utc)
    assignments = [_homework(item) for item in homework]
    assignments.sort(
        key=lambda item: (
            str(item["due"]),
            bool(item["done"]),
            str(item["subject"]).casefold(),
            str(item["id"]),
        )
    )

    student_data = {
        "name": _text(getattr(student, "name", "")),
        "class": _text(getattr(student, "class_name", "")),
        "establishment": _text(getattr(student, "establishment", "")),
    }
    canonical = json.dumps(
        {"student": student_data, "homework": assignments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    content_hash = hashlib.sha256(canonical).hexdigest()

    pending = sum(not bool(item["done"]) for item in assignments)
    due_dates = [str(item["due"]) for item in assignments if not item["done"]]

    return {
        "schema_version": 1,
        "generated_at": generated_at.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "content_hash": content_hash,
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "student": student_data,
        "summary": {
            "total": len(assignments),
            "pending": pending,
            "done": len(assignments) - pending,
            "next_due": min(due_dates) if due_dates else None,
        },
        "homework": assignments,
    }


def encode_snapshot(snapshot: dict[str, object]) -> bytes:
    """Encode a compact, deterministic UTF-8 JSON document."""
    return (
        json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
