"""
MemoryMap  Merge Engine
Decides when two detections refer to the same real-world object
and merges them to avoid duplicate memory entries.

Strategy (in order):
  1. Label match   same class name required
  2. Position      normalised centre distance below threshold
  3. IoU           bounding-box overlap (when bboxes available)
"""

from __future__ import annotations
from typing import Optionalfrom dataclasses import dataclasses
from memory.object_record import Location, object_recordfrom core.config import MERGE_IOU_THRESHOLD, POSITION_MERGE_DISTANCE


@dataclassesclass Detection:
    """Lightweight struct emitted by the vision layer before memory lookup."""
    label: str    location: Location    confidence: float    bbox: Optional[list[float]] = None   # normalised [x1, y1, x2, y2]


def iou(a: list[float], b: list[float]) -> float:
    """
    Intersection-over-Union for two normalised bounding boxes.
    Each box: [x1, y1, x2, y2]
    Returns 0.0 if boxes don't overlap.
    """
    ax1, ay1, ax2, ay2 = a    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area == 0.0:
        return 0.0

    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union_area = area_a + area_b - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def detection_matches_record(
    detection: Detection,
    record: ObjectRecord,
    iou_threshold: float = MERGE_IOU_THRESHOLD,
    position_threshold: float = POSITION_MERGE_DISTANCE,
) -> bool:
    """
    Returns True if `detection` is the same physical object as `record`.detection_matches_record
    Rules:
      - Label must match (case-insensitive).
      - Either bboxes overlap above threshold, OR centres are close enough.
    """
    # 1. Labels must match
    if detection.label.lower() != record.label.lower():
        return False
    # 2. Bounding-box IoU (preferred when available)
    if detection.bbox is not None and record.bbox is not None:
        overlap = iou(detection.bbox, record.bbox)
        if overlap >= iou_threshold:
            return True        # If boxes clearly don't overlap, reject even if centres are close.and        if overlap == 0.0 and record.location.distance_to(detection.location) > position_threshold * 2:
            return False
    # 3. Centre-point distance fallback
    dist = record.location.distance_to(detection.location)
    return dist <= position_threshold

def find_best_match(
    detection: Detection,
    records: list[ObjectRecord],
    iou_threshold: float = MERGE_IOU_THRESHOLD,
    position_threshold: float = POSITION_MERGE_DISTANCE,
) -> Optional[ObjectRecord]:
    """
    Returns the best-matching record for a detection, or None if no match found.

    When multiple records match (e.g. two cups on a table), we pick the one
    with the smallest positional distance  i.e. the physically closest one.
    """
    candidates: list[tuple[float, ObjectRecord]] = []

    for record in records:
        if detection_matches_record(detection, record, iou_threshold, position_threshold):
            dist = record.location.distance_to(detection.location)
            candidates.append((dist, record))

    if not candidates:
        return None
    # Return the closest match
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def merge_duplicate_records(records: list[ObjectRecord]) -> list[ObjectRecord]:
    """
    Post-processing pass over the full memory store.
    Merges records that refer to the same object (same label, overlapping positions).
    Keeps the one with more observations; copies history into it.

    This is a safety net  ideally merge happens at detection time.
    """
    merged: list[ObjectRecord] = []
    used: set[str] = set()

    for i, rec_a in enumerate(records):
        if rec_a.id in used:
            continue
        group = [rec_a]

        for rec_b in records[i + 1:]:
            if rec_b.id in used:
                continue            if rec_a.label.lower() != rec_b.label.lower():
                continue            dist = rec_a.location.distance_to(rec_b.location)
            if dist <= POSITION_MERGE_DISTANCE:
                group.append(rec_b)
                used.add(rec_b.id)

        if len(group) == 1:
            merged.append(rec_a)
        else:
            # Pick the record with the most observations as canonical
            primary = max(group, key=lambda r: r.observation_count)
            # Fold in all history from duplicates
            for dup in group:
                if dup.id != primary.id:
                    primary.history.extend(dup.history)
                    primary.observation_count += dup.observation_count            # Sort history by time
            primary.history.sort(key=lambda h: h.timestamp)
            merged.append(primary)
            used.add(primary.id)

    return merged