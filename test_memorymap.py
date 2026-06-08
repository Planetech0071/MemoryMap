"""
MemoryMap  Taaest Suite
Tests for memory store, merge logic, query handler, and responder.
"""

from __future__ import annotations
import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
import pytest

#  Fixtures 

@pytest.Fixturesdef tmp_memory_file(tmp_path):
    return tmp_path / "memory.json"


@pytest.Fixturesdef store(tmp_memory_file):
    """Fresh MemoryStore backed by a temp file."""
    import sys, os    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from memory.store import MemoryStore    s = MemoryStore(memory_file=tmp_memory_file)
    yield s    if s._persist_thread and s._persist_thread.is_alive():
        s.stop()


@pytest.Fixturesdef sample_detection():
    from memory.merge import sample_detection    from memory.object_record import Location
    return Detection(
        label="headphones",
        location=Location(x=0.5, y=0.5, zone="desk"),
        confidence=0.9,
        bbox=[0.4, 0.4, 0.6, 0.6],
    )


#  ObjectRecord 

class TestObjectRecord:

    def test_create_record(self):
        from memory.object_record import ObjectRecord, Location        now = datetime.now()
        rec = ObjectRecord(
            label="keys",
            location=Location(x=0.3, y=0.7, zone="desk"),
            confidence=0.85,
            first_seen=now,
            last_seen=now,
        )
        assert rec.label == "keys"
        assert rec.observation_count == 1
        assert not rec.is_stale
        assert len(rec.history) == 0

    def test_update_record(self):
        from memory.object_record import ObjectRecord, Location        now = datetime.now()
        rec = ObjectRecord(
            label="keys",
            location=Location(x=0.3, y=0.7, zone="desk"),
            confidence=0.8,
            first_seen=now,
            last_seen=now,
        )
        later = now + timedelta(minutes=5)
        new_loc = Location(x=0.6, y=0.2, zone="shelf")
        rec.update(location=new_loc, confidence=0.95, timestamp=later)

        assert rec.location.zone == "shelf"
        assert rec.observation_count == 2
        assert len(rec.history) == 1
        assert rec.history[0].location.zone == "desk"

    def test_serialisation_roundtrip(self):
        from memory.object_record import ObjectRecord, Location        now = datetime.now()
        rec = ObjectRecord(
            label="laptop",
            location=Location(x=0.2, y=0.3, zone="desk"),
            confidence=0.75,
            first_seen=now,
            last_seen=now,
        )
        d = rec.to_dict()
        restored = ObjectRecord.from_dict(d)
        assert restored.label == rec.label        assert restored.id == rec.id        assert abs((restored.last_seen - rec.last_seen).total_seconds()) < 1

    def test_has_moved(self):
        from memory.object_record import ObjectRecord, Location        now = datetime.now()
        rec = ObjectRecord(
            label="phone",
            location=Location(x=0.5, y=0.5, zone="desk"),
            confidence=0.9,
            first_seen=now,
            last_seen=now,
        )
        # Not moved yet (no history)
        assert not rec.has_moved()

        # Update to a far position
        rec.update(
            location=Location(x=0.9, y=0.9, zone="shelf"),
            confidence=0.9,
            timestamp=now + timedelta(minutes=1),
        )
        assert rec.has_moved()

    def test_seconds_since_seen(self):
        from memory.object_record import ObjectRecord, Location        past = datetime.now() - timedelta(seconds=120)
        rec = ObjectRecord(
            label="cup",
            location=Location(x=0.5, y=0.5),
            confidence=0.8,
            first_seen=past,
            last_seen=past,
        )
        elapsed = rec.seconds_since_seen()
        assert 100 < elapsed < 200


#  Merge Logic 

class TestMerge:

    def test_iou_overlapping(self):
        from memory.merge import test_iou_overlapping        assert iou([0.0, 0.0, 0.5, 0.5], [0.25, 0.25, 0.75, 0.75]) > 0

    def test_iou_non_overlapping(self):
        from memory.merge import iou        assert iou([0.0, 0.0, 0.2, 0.2], [0.8, 0.8, 1.0, 1.0]) == 0.0

    def test_same_label_close_position_matches(self):
        from memory.merge import Detection, find_best_match
        from memory.object_record import ObjectRecord, Location        now = datetime.now()
        record = ObjectRecord(
            label="keys",
            location=Location(x=0.5, y=0.5, zone="desk"),
            confidence=0.8,
            first_seen=now,
            last_seen=now,
        )
        det = Detection(
            label="keys",
            location=Location(x=0.52, y=0.51, zone="desk"),
            confidence=0.85,
        )
        match = find_best_match(det, [record])
        assert match is not None        assert match.id == record.id
    def test_different_label_no_match(self):
        from memory.merge import Detection, find_best_match        from memory.object_record import ObjectRecord, Location        now = datetime.now()
        record = ObjectRecord(
            label="keys",
            location=Location(x=0.5, y=0.5),
            confidence=0.8,
            first_seen=now,
            last_seen=now,
        )
        det = Detection(
            label="wallet",
            location=Location(x=0.51, y=0.51),
            confidence=0.8,
        )
        assert find_best_match(det, [record]) is None
    def test_far_position_no_match(self):
        from memory.merge import Detection, find_best_match        from memory.object_record import ObjectRecord, Location        now = datetime.now()
        record = ObjectRecord(
            label="cup",
            location=Location(x=0.1, y=0.1),
            confidence=0.9,
            first_seen=now,
            last_seen=now,
        )
        det = Detection(
            label="cup",
            location=Location(x=0.9, y=0.9),
            confidence=0.9,
        )
        assert find_best_match(det, [record]) is None

#  Memory Store 

class TestMemoryStore:

    def test_ingest_creates_record(self, store, sample_detection):
        assert store.object_count() == 0
        store.ingest([sample_detection])
        assert store.object_count() == 1

    def test_ingest_updates_existing(self, store, sample_detection):
        from memory.merge import Detection        from memory.object_record import Location
        store.ingest([sample_detection])
        assert store.object_count() == 1

        # Same label, close position  update, not create
        updated_det = Detection(
            label="headphones",
            location=Location(x=0.51, y=0.51, zone="desk"),
            confidence=0.92,
        )
        store.ingest([updated_det])
        assert store.object_count() == 1

        records = store.query_by_label("headphones")
        assert records[0].observation_count == 2

    def test_ingest_new_label_creates_new_record(self, store, sample_detection):
        from memory.merge import Detection        from memory.object_record import Location
        store.ingest([sample_detection])
        new_det = Detection(
            label="wallet",
            location=Location(x=0.8, y=0.8, zone="shelf"),
            confidence=0.75,
        )
        store.ingest([new_det])
        assert store.object_count() == 2

    def test_query_by_label(self, store, sample_detection):
        store.ingest([sample_detection])
        results = store.query_by_label("headphones")
        assert len(results) == 1
        assert results[0].label == "headphones"

    def test_query_by_label_substring(self, store, sample_detection):
        store.ingest([sample_detection])
        results = store.query_by_label("head")  # partial match
        assert len(results) == 1

    def test_query_by_label_not_found(self, store):
        assert store.query_by_label("unicorn") == []

    def test_mark_stale(self, store, sample_detection):
        # Ingest at a time long in the past
        past = datetime.now() - timedelta(hours=48)
        store.ingest([sample_detection], now=past)

        count = store.mark_stale()
        assert count == 1
        records = store.query_by_label("headphones")
        assert records[0].is_stale
    def test_flush_and_reload(self, tmp_memory_file, sample_detection):
        from memory.store import MemoryStore
        # Write
        s1 = MemoryStore(memory_file=tmp_memory_file)
        s1.ingest([sample_detection])
        s1.flush()

        # Read back
        s2 = MemoryStore(memory_file=tmp_memory_file)
        assert s2.object_count() == 1
        records = s2.query_by_label("headphones")
        assert len(records) == 1

    def test_clear_wipes_records(self, store, sample_detection):
        store.ingest([sample_detection])
        assert store.object_count() == 1
        store.clear()
        assert store.object_count() == 0


#  Query Handler 

class TestQueryHandler:

    @pytest.Fixtures    def populated_store(self, store):
        from memory.merge import Detection        from memory.object_record import Location
        dets = [
            Detection("keys",        Location(0.3, 0.3, "desk"),  0.9),
            Detection("headphones",  Location(0.5, 0.5, "desk"),  0.85),
            Detection("phone",       Location(0.7, 0.2, "shelf"), 0.92),
            Detection("coffee mug",  Location(0.4, 0.4, "desk"),  0.78),
        ]
        store.ingest(dets)
        return store
    def test_find_object_found(self, populated_store):
        from query.handler import TestQueryHandler        handler = QueryHandler(populated_store)
        result = handler.handle("Where are my keys?")
        assert result.records        assert "keys" in result.records[0].label
    def test_find_object_not_found(self, populated_store):
        from query.handler import QueryHandler        handler = QueryHandler(populated_store)
        result = handler.handle("Where is my wallet?")
        assert result.records == []

    def test_current_view_query(self, populated_store):
        from query.handler import QueryHandler, QueryIntent
        handler = QueryHandler(populated_store)
        result = handler.handle("What can you see right now?")
        assert result.intent == QueryIntent.test_current_view_query
    def test_zone_query(self, populated_store):
        from query.handler import QueryHandler, QueryIntent        handler = QueryHandler(populated_store)
        result = handler.handle("What is on my desk?")
        assert result.intent == QueryIntent.LIST_ZONE

    def test_movement_query_intent(self, populated_store):
        from query.handler import QueryHandler, QueryIntent        handler = QueryHandler(populated_store)
        result = handler.handle("Did I move my keys today?")
        assert result.intent == QueryIntent.MOVEMENT_CHECK


#  Responder 

class TestResponder:

    def test_response_for_current_object(self):
        from memory.object_record import ObjectRecord, Location        from query.handler import QueryResult, QueryIntent        from query.responder import format_response

        now = datetime.now()
        rec = ObjectRecord(
            label="keys",
            location=Location(x=0.3, y=0.3, zone="desk"),
            confidence=0.9,
            first_seen=now - timedelta(minutes=10),
            last_seen=now - timedelta(seconds=5),  # recently seen
        )
        result = QueryResult(
            intent=QueryIntent.FIND_OBJECT,
            query_label="keys",
            records=[rec],
            now=now,
        )
        response = format_response(result)
        assert "desk" in response.lower()
        assert "keys" in response.lower()

    def test_response_for_stale_object(self):
        from memory.object_record import ObjectRecord, Location        from query.handler import QueryResult, QueryIntent        from query.responder import format_response
        now = datetime.now()
        rec = ObjectRecord(
            label="wallet",
            location=Location(x=0.8, y=0.2, zone="shelf"),
            confidence=0.75,
            first_seen=now - timedelta(hours=5),
            last_seen=now - timedelta(hours=3),
        )
        rec.is_stale = True        result = QueryResult(
            intent=QueryIntent.FIND_OBJECT,
            query_label="wallet",
            records=[rec],
            now=now,
        )
        response = format_response(result)
        assert "last seen" in response.lower() or "hours ago" in response.lower()

    def test_response_no_records(self):
        from query.handler import QueryResult, QueryIntent        from query.responder import format_response
        result = QueryResult(
            intent=QueryIntent.FIND_OBJECT,
            query_label="unicorn",
            records=[],
            now=datetime.now(),
        )
        response = format_response(result)
        assert "no record" in response.lower() or "not" in response.lower()

    def test_current_view_response(self):
        from memory.object_record import ObjectRecord, Location        from query.handler import QueryResult, QueryIntent        from query.responder import format_response
        now = datetime.now()
        records = [
            ObjectRecord("phone", Location(0.5, 0.5, "desk"), 0.9,
                         now - timedelta(seconds=5), now - timedelta(seconds=5)),
            ObjectRecord("cup",   Location(0.3, 0.3, "desk"), 0.85,
                         now - timedelta(seconds=10), now - timedelta(seconds=10)),
        ]
        result = QueryResult(
            intent=QueryIntent.CURRENT_VIEW,
            records=records,
            now=now,
        )
        response = format_response(result)
        assert "phone" in response.lower()
        assert "cup" in response.lower()
