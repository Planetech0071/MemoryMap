"""
MemoryMap — ObjectRecord
The fundamental unit of spatial memory.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Location:
    """Normalised (0-1) position within the camera frame, plus optional zone label."""
    x: float          # horizontal centre, 0 = left, 1 = right
    y: float          # vertical centre,   0 = top,  1 = bottom
    zone: str = "general"

    def distance_to(self, other: "Location") -> float:
        """Euclidean distance in normalised space."""
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5

    def to_dict(self) -> dict:
        return {"x": round(self.x, 4), "y": round(self.y, 4), "zone": self.zone}

    @classmethod
    def from_dict(cls, d: dict) -> "Location":
        return cls(x=d["x"], y=d["y"], zone=d.get("zone", "general"))


@dataclass
class HistoryEntry:
    """A single observation snapshot stored in movement history."""
    timestamp: datetime
    location: Location
    confidence: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "location": self.location.to_dict(),
            "confidence": round(self.confidence, 3),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryEntry":
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            location=Location.from_dict(d["location"]),
            confidence=d["confidence"],
        )


@dataclass
class ObjectRecord:
    """
    One persistent memory entry for a tracked object.

    Lifecycle:
      - Created on first detection.
      - Updated on each subsequent sighting.
      - Marked stale if not seen for MEMORY_DECAY_HOURS.
    """

    label: str                          # human-readable class name, e.g. "keys"
    location: Location                  # most recent position
    confidence: float                   # most recent detection confidence
    first_seen: datetime                # when first detected
    last_seen: datetime                 # when last detected

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    observation_count: int = 1
    history: list[HistoryEntry] = field(default_factory=list)
    is_stale: bool = False              # set by memory store based on decay rules

    # Optional: bounding box in normalised coords [x1,y1,x2,y2]
    bbox: Optional[list[float]] = None

    # ── Update ─────────────────────────────────────────────────────────────

    def update(
        self,
        location: Location,
        confidence: float,
        timestamp: datetime,
        bbox: Optional[list[float]] = None,
        max_history: int = 50,
    ) -> None:
        """Record a new sighting of this object."""
        # Append current state to history before overwriting
        self.history.append(
            HistoryEntry(
                timestamp=self.last_seen,
                location=self.location,
                confidence=self.confidence,
            )
        )
        # Trim history to max length (oldest first)
        if len(self.history) > max_history:
            self.history = self.history[-max_history:]

        self.location = location
        self.confidence = confidence
        self.last_seen = timestamp
        self.observation_count += 1
        self.bbox = bbox
        self.is_stale = False

    # ── Queries ────────────────────────────────────────────────────────────

    def seconds_since_seen(self, now: Optional[datetime] = None) -> float:
        """Seconds elapsed since last sighting."""
        now = now or datetime.now()
        return (now - self.last_seen).total_seconds()

    def has_moved(self, threshold: float = 0.08) -> bool:
        """True if the object's last two recorded positions differ meaningfully."""
        if not self.history:
            return False
        prev = self.history[-1].location
        return self.location.distance_to(prev) > threshold

    def zone_at(self, timestamp: datetime) -> str:
        """Returns zone label at a given time (approximate, from history)."""
        # Walk history backwards to find the closest entry
        for entry in reversed(self.history):
            if entry.timestamp <= timestamp:
                return entry.location.zone
        return self.location.zone

    # ── Serialisation ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "location": self.location.to_dict(),
            "confidence": round(self.confidence, 3),
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "observation_count": self.observation_count,
            "is_stale": self.is_stale,
            "bbox": self.bbox,
            "history": [h.to_dict() for h in self.history],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ObjectRecord":
        obj = cls(
            id=d["id"],
            label=d["label"],
            location=Location.from_dict(d["location"]),
            confidence=d["confidence"],
            first_seen=datetime.fromisoformat(d["first_seen"]),
            last_seen=datetime.fromisoformat(d["last_seen"]),
            observation_count=d.get("observation_count", 1),
            is_stale=d.get("is_stale", False),
            bbox=d.get("bbox"),
        )
        obj.history = [HistoryEntry.from_dict(h) for h in d.get("history", [])]
        return obj

    def __repr__(self) -> str:
        return (
            f"ObjectRecord(label={self.label!r}, zone={self.location.zone!r}, "
            f"confidence={self.confidence:.2f}, last_seen={self.last_seen.strftime('%H:%M:%S')})"
        )
