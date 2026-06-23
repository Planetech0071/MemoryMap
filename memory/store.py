"""
MemoryMap — Memory Store
Thread-safe, disk-backed store of ObjectRecords.

Responsibilities:
  - Ingest new detections (create or update records)
  - Periodically flush to disk (JSON)
  - Mark stale objects
  - Provide query primitives (by label, zone, recency)
"""

from __future__ import annotations
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

from loguru import logger

from core.config import (
    MAX_HISTORY_ENTRIES,
    MEMORY_DECAY_HOURS,
    MEMORY_FILE,
    PERSIST_INTERVAL_SEC,
)
from memory.merge import Detection, find_best_match, merge_duplicate_records
from memory.object_record import Location, ObjectRecord


class MemoryStore:
    """
    Central in-memory store for all tracked objects.

    Usage:
        store = MemoryStore()
        store.start()                     # begins background persist loop

        store.ingest(detections, now)     # called each camera cycle
        store.query_by_label("keys")      # returns list[ObjectRecord]
        store.all_current()               # objects seen recently
    """

    def __init__(self, memory_file: Path = MEMORY_FILE) -> None:
        self._records: dict[str, ObjectRecord] = {}  # id → record
        self._lock = threading.RLock()
        self._memory_file = memory_file
        self._last_persist: float = 0.0
        self._persist_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._load_from_disk()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start background persistence + staleness-check thread."""
        self._stop_event.clear()
        self._persist_thread = threading.Thread(
            target=self._background_loop,
            daemon=True,
            name="memorymap-persist",
        )
        self._persist_thread.start()
        logger.info("MemoryStore started (persist every {}s)", PERSIST_INTERVAL_SEC)

    def stop(self) -> None:
        """Gracefully stop background thread and flush to disk."""
        self._stop_event.set()
        if self._persist_thread:
            self._persist_thread.join(timeout=5)
        self.flush()
        logger.info("MemoryStore stopped and flushed.")

    # ── Ingestion ──────────────────────────────────────────────────────────

    def ingest(self, detections: list[Detection], now: Optional[datetime] = None) -> None:
        """
        Process a batch of detections from one camera frame.
        For each detection:
        - If a matching record exists → update it
        - Otherwise → create a new record
        """
        now = now or datetime.now()

        with self._lock:
            records = list(self._records.values())

            for det in detections:
                match = find_best_match(det, records)

                if match is not None:
                    match.update(
                        location=det.location,
                        confidence=det.confidence,
                        timestamp=now,
                        bbox=det.bbox,
                        max_history=MAX_HISTORY_ENTRIES,
                    )
                    logger.debug("Updated: {}", match)
                else:
                    new_record = ObjectRecord(
                        label=det.label,
                        location=det.location,
                        confidence=det.confidence,
                        first_seen=now,
                        last_seen=now,
                        bbox=det.bbox,
                    )
                    self._records[new_record.id] = new_record
                    # Keep records list in sync for subsequent detections in this batch
                    records.append(new_record)
                    logger.info("New object: {}", new_record)

    # ── Staleness ──────────────────────────────────────────────────────────

    def mark_stale(self, now: Optional[datetime] = None) -> int:
        """
        Mark records as stale if not seen for MEMORY_DECAY_HOURS.
        Returns count of newly-stale records.
        """
        now = now or datetime.now()
        cutoff = timedelta(hours=MEMORY_DECAY_HOURS)
        count = 0

        with self._lock:
            for record in self._records.values():
                was_stale = record.is_stale
                record.is_stale = (now - record.last_seen) > cutoff
                if record.is_stale and not was_stale:
                    count += 1
                    logger.debug("Marked stale: {}", record)

        return count

    # ── Query Primitives ───────────────────────────────────────────────────

    def all(self) -> list[ObjectRecord]:
        """All records, including stale ones."""
        with self._lock:
            return list(self._records.values())

    def all_current(self, within_seconds: Optional[float] = None) -> list[ObjectRecord]:
        """
        Records seen recently (non-stale).
        If within_seconds given, restricts to that window.
        """
        now = datetime.now()
        window = timedelta(seconds=within_seconds) if within_seconds else None
        with self._lock:
            results = []
            for r in self._records.values():
                if r.is_stale:
                    continue
                if window and (now - r.last_seen) > window:
                    continue
                results.append(r)
        return results

    def query_by_label(
        self,
        label: str,
        include_stale: bool = True,
    ) -> list[ObjectRecord]:
        """
        Find all records matching a label (case-insensitive substring match).
        Returns most recently seen first.
        """
        label_lower = label.lower()

        with self._lock:
            results = [
                r for r in self._records.values()
                if label_lower in r.label.lower()
                and (include_stale or not r.is_stale)
            ]
            results.sort(key=lambda r: r.last_seen, reverse=True)
        return results

    def query_by_zone(self, zone: str) -> list[ObjectRecord]:
        """All non-stale objects currently in a named zone."""
        zone_lower = zone.lower()
        with self._lock:
            return [
                r for r in self._records.values()
                if r.location.zone.lower() == zone_lower and not r.is_stale
            ]

    def get_by_id(self, record_id: str) -> Optional[ObjectRecord]:
        with self._lock:
            return self._records.get(record_id)

    def object_count(self) -> int:
        with self._lock:
            return len(self._records)

    def __iter__(self) -> Iterator[ObjectRecord]:
        with self._lock:
            yield from list(self._records.values())

    # ── Persistence ────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Write current memory to disk as JSON."""
        with self._lock:
            data = {
                "version": 1,
                "saved_at": datetime.now().isoformat(),
                "records": {rid: r.to_dict() for rid, r in self._records.items()},
            }

        try:
            tmp = self._memory_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(self._memory_file)
            logger.debug("Memory flushed ({} records).", len(self._records))
        except Exception as exc:
            logger.error("Failed to persist memory: {}", exc)

    def clear(self) -> None:
        """Wipe all records (also clears disk file)."""
        with self._lock:
            self._records.clear()
        self.flush()
        logger.warning("Memory store cleared.")

    def run_merge_pass(self) -> int:
        """
        Perform a full duplicate-merge pass over all records.
        Returns the number of records removed.
        """
        with self._lock:
            before = len(self._records)
            merged = merge_duplicate_records(list(self._records.values()))
            self._records = {r.id: r for r in merged}
            removed = before - len(self._records)
            if removed:
                logger.info("Merge pass removed {} duplicate(s).", removed)

        return removed

    # ── Private ────────────────────────────────────────────────────────────

    def _load_from_disk(self) -> None:
        if not self._memory_file.exists():
            logger.info("No memory file found at {}. Starting fresh.", self._memory_file)
            return
        try:
            raw = json.loads(self._memory_file.read_text(encoding="utf-8"))
            for rid, record_dict in raw.get("records", {}).items():
                record = ObjectRecord.from_dict(record_dict)
                self._records[rid] = record
            logger.info(
                "Loaded {} records from {}.",
                len(self._records),
                self._memory_file,
            )
        except Exception as exc:
            logger.error("Failed to load memory file: {}. Starting fresh.", exc)

    def _background_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(1)
            now = datetime.now()

            # Periodic persist
            if (now.timestamp() - self._last_persist) >= PERSIST_INTERVAL_SEC:
                self.flush()
                self.mark_stale(now)
                self._last_persist = now.timestamp()
