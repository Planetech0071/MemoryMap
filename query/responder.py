"""
MemoryMap — Responder
Formats QueryResult objects into calm, direct, temporally-aware text.

Design principles (from spec):
  - Short and direct
  - Avoid guessing without evidence
  - Clearly separate "seen now" vs "last seen"
  - Avoid overconfidence
  - Report uncertainty honestly
"""

from __future__ import annotations

from datetime import datetime, timedelta

from query.handler import QueryIntent, QueryResult
from memory.object_record import HistoryEntry
from core.config import CURRENT_VISIBLE_WINDOW_SEC


def _time_ago(dt: datetime, now: datetime) -> str:
    """
    Human-readable relative time string.
    Examples: "just now", "5 minutes ago", "2 hours ago", "yesterday"
    """
    delta = now - dt
    seconds = int(delta.total_seconds())

    if seconds < 10:
        return "just now"
    if seconds < 60:
        return f"{seconds} seconds ago"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def _is_current(record, now: datetime) -> bool:
    """True if object is considered 'currently visible'."""
    return (now - record.last_seen).total_seconds() <= CURRENT_VISIBLE_WINDOW_SEC


def format_response(result: QueryResult) -> str:
    """Main entry point: turn a QueryResult into a human-readable string."""

    now = result.now
    intent = result.intent

    # ── Unknown / no label ────────────────────────────────────────────────
    if intent == QueryIntent.UNKNOWN:
        return (
            "I didn't understand that query. "
            "Try asking 'Where is my X?' or 'What's on my desk?'"
        )

    # ── Current view ──────────────────────────────────────────────────────
    if intent == QueryIntent.CURRENT_VIEW:
        if not result.records:
            return "Nothing is currently visible in the camera view."

        labels = sorted({r.label for r in result.records})
        label_list = _join_labels(labels)
        return f"Currently visible: {label_list}."

    # ── List zone ─────────────────────────────────────────────────────────
    if intent == QueryIntent.LIST_ZONE:
        zone = result.query_zone or "that area"

        if not result.records:
            return f"I don't see anything in the {zone} right now."

        labels = sorted({r.label for r in result.records})
        label_list = _join_labels(labels)
        return f"On the {zone} right now: {label_list}."

    # ── No records found ──────────────────────────────────────────────────
    label = result.query_label or "that object"

    if not result.records:
        return (
            f"I have no record of {_article(label)} {label}. "
            "It may not have been seen by the camera yet."
        )

    record = result.records[0]  # Best match (most recent)

    # ── Last seen ─────────────────────────────────────────────────────────
    if intent == QueryIntent.LAST_SEEN:
        when = _time_ago(record.last_seen, now)
        zone = record.location.zone
        conf_note = _confidence_note(record.confidence)
        return (
            f"Your {label} was last seen on the {zone} {when}{conf_note}."
        )

    # ── Movement check ────────────────────────────────────────────────────
    if intent == QueryIntent.MOVEMENT_CHECK:
        if not record.history:
            return (
                f"I've only seen your {label} once — on the "
                f"{record.location.zone}, {_time_ago(record.last_seen, now)}. "
                "No movement history yet."
            )

        # Check if position has changed significantly today
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_entries = [
            h for h in record.history
            if h.timestamp >= today_start
        ]

        if not today_entries:
            return (
                f"Your {label} hasn't been seen today. "
                f"Last recorded location: {record.location.zone}, "
                f"{_time_ago(record.last_seen, now)}."
            )

        # Check how many distinct zones appear today
        zones_today = {h.location.zone for h in today_entries}
        zones_today.add(record.location.zone)

        if len(zones_today) > 1:
            zone_sequence = _build_zone_sequence(record, today_start, now)
            return f"Yes — your {label} moved today: {zone_sequence}."
        else:
            zone = record.location.zone
            return (
                f"Your {label} has stayed on the {zone} all day. "
                f"Last confirmed {_time_ago(record.last_seen, now)}."
            )

    # ── Find object (default) ─────────────────────────────────────────────
    if _is_current(record, now):
        zone = record.location.zone
        conf_note = _confidence_note(record.confidence)
        return f"Your {label} is currently on the {zone}{conf_note}."
    else:
        when = _time_ago(record.last_seen, now)
        zone = record.location.zone
        conf_note = _confidence_note(record.confidence)

        stale_note = ""
        if record.is_stale:
            stale_note = " This record is quite old — the object may have moved."

        return (
            f"Your {label} was last seen on the {zone} {when}{conf_note}.{stale_note}"
        )


# ── Helpers ───────────────────────────────────────────────────────────────

def _article(word: str) -> str:
    """Return 'an' if word starts with a vowel sound, else 'a'."""
    return "an" if word and word[0].lower() in "aeiou" else "a"


def _join_labels(labels: list[str]) -> str:
    """Join a list of labels naturally: 'a, b, and c'."""
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _confidence_note(conf: float) -> str:
    """Produce a confidence caveat if conf is below threshold."""
    if conf >= 0.85:
        return ""
    if conf >= 0.65:
        return " (moderate confidence)"
    return " (low confidence — may be misidentified)"


def _build_zone_sequence(record, since: datetime, now: datetime) -> str:
    """
    Build a readable movement narrative:
    "near the door at 08:14, then moved to the desk at 12:03"
    """
    entries = [h for h in record.history if h.timestamp >= since]
    # Add current position
    entries.append(
        HistoryEntry(
            timestamp=record.last_seen,
            location=record.location,
            confidence=record.confidence,
        )
    )
    entries.sort(key=lambda e: e.timestamp)

    # Collapse consecutive same-zone entries
    collapsed: list[HistoryEntry] = []
    for entry in entries:
        if not collapsed or collapsed[-1].location.zone != entry.location.zone:
            collapsed.append(entry)

    if not collapsed:
        return f"on the {record.location.zone}"

    parts = []
    for i, entry in enumerate(collapsed):
        time_str = entry.timestamp.strftime("%H:%M")
        zone = entry.location.zone
        if i == 0:
            parts.append(f"on the {zone} at {time_str}")
        else:
            parts.append(f"moved to the {zone} at {time_str}")

    return ", then ".join(parts)
