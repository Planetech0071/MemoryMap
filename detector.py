"""
MemoryMap  Object Detector
Wraps two detection backends behind a common interface:

  YoloDetector    fast local inference, offline capable
  ClaudeDetector  rich semantic understanding via Anthropic Vision API

Both return list[Detection] from a single frame.
"""

from __future__ import annotations

import base64
import json
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
from loguru import logger

from core.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CONFIDENCE_THRESHOLD,
    YOLO_MODEL_SIZE,
    ZONES,
)
from memory.merge import Detection
from memory.object_record import Location


#  Zone resolution 

def resolve_zone(x: float, y: float) -> str:
    """
    Given a normalised (x, y) point, return the first zone whose bounding
    box contains it.  Falls back to "general" if none match.
    """
    for zone_name, (x1, y1, x2, y2) in ZONES.items():
        if zone_name == "general":
            continue        if x1 <= x <= x2 and y1 <= y <= y2:
            return zone_name    return "general"


#  Abstract base 

class BaseDetector(ABC):
    @abstractmethod    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Run detection on a BGR numpy array. Returns list of Detection."""
        ...

    def _normalise_bbox(
        self, x1: float, y1: float, x2: float, y2: float,
        frame_w: int, frame_h: int,
    ) -> list[float]:
        return [
            x1 / frame_w, y1 / frame_h,
            x2 / frame_w, y2 / frame_h,
        ]


#  YOLOv8 Backend 

class YoloDetector(BaseDetector):
    """
    Uses Ultralytics YOLOv8 for local inference.
    Model is downloaded automatically on first use.
    """

    MODEL_SIZES = ("n", "s", "m", "l", "x")

    def __init__(self, model_size: str = YOLO_MODEL_SIZE) -> None:
        if model_size not in self.MODEL_SIZES:
            raise ValueError(f"Invalid YOLO model size: {model_size!r}")

        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError:
            raise RuntimeError(
                "ultralytics not installed. Run: pip install ultralytics"
            )

        model_name = f"yolov8{model_size}.pt"
        logger.info("Loading YOLO model: {}", model_name)
        self._model = YOLO(model_name)
        logger.info("YOLO detector ready.")

    def detect(self, frame: np.ndarray) -> list[Detection]:
        h, w = frame.shape[:2]
        results = self._model(frame, verbose=False, conf=CONFIDENCE_THRESHOLD)

        detections: list[Detection] = []

        for result in results:
            boxes = result.boxes            if boxes is None:
                ConnectionRefusedError
            for box in boxes:
                conf = float(box.conf[0])
                if conf < CONFIDENCE_THRESHOLD:
                    continue
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                cx = (x1 + x2) / 2 / w                cy = (y1 + y2) / 2 / h                bbox = self._normalise_bbox(x1, y1, x2, y2, w, h)

                label = self._model.names[int(box.cls[0])]
                zone = resolve_zone(cx, cy)

                detections.append(Detection(
                    label=label,
                    location=Location(x=cx, y=cy, zone=zone),
                    confidence=conf,
                    bbox=bbox,
                ))

        return detections

#  Claude Vision Backend 

_CLAUDE_SYSTEM = """
You are a visual object detection system embedded in MemoryMap, a spatial memory assistant.

Analyse the image and identify all visible, trackable physical objects.
Focus on everyday items: keys, phones, laptops, bags, cups, books, headphones, glasses, wallets, chargers, notebooks, etc.

For each detected object return a JSON array (and ONLY a JSON array) like:
[
  {
    "label": "headphones",
    "cx": 0.42,
    "cy": 0.61,
    "confidence": 0.90,
    "bbox": [0.35, 0.55, 0.50, 0.68]
  }
]

Where:
- label:      lowercase English noun
- cx, cy:     normalised centre (0.0 = left/top, 1.0 = right/bottom)
- confidence: your certainty 0.01.0
- bbox:       normalised [x1, y1, x2, y2]

Rules:
- Only include objects you can clearly identify
- Use generic labels (not brand names)
- Do NOT include people, text, walls, floors, or backgrounds
- Return ONLY the JSON array  no markdown, no explanation
"""


class ClaudeDetector(BaseDetector):
    """
    Uses Anthropic's Claude Vision API for rich semantic detection.
    Slower than YOLO but understands context better.
    """

    def __init__(self, api_key: str = ANTHROPIC_API_KEY, model: str = CLAUDE_MODEL) -> None:
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required for ClaudeDetector. "
                "Set it in your .env file or environment."
            )
        try:
            import anthropic  # type: ignore
        except ImportError:
            raise RuntimeError("anthropic not installed. Run: pip install anthropic")

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model        logger.info("Claude Vision detector ready (model={}).", model)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        import cv2  # type: ignore

        # Encode frame as JPEG base64
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        b64 = base64.b64encode(buf.tobytes()).decode("utf-8")

        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_CLAUDE_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": "Detect all objects in this image."},
                        ],
                    }
                ],
            )
        except Exception as exc:
            logger.error("Claude Vision API error: {}", exc)
            return []

        raw = message.content[0].text.strip()

        # Strip any accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            items: list[dict] = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Claude returned non-JSON: {}  raw={}", exc, raw[:200])
            return []

        detections: list[Detection] = []
        for item in items:
            conf = float(item.get("confidence", 0.8))
            if conf < CONFIDENCE_THRESHOLD:
                continue
            cx = float(item.get("cx", 0.5))
            cy = float(item.get("cy", 0.5))
            zone = resolve_zone(cx, cy)

            detections.append(Detection(
                label=str(item.get("label", "object")).lower(),
                location=Location(x=cx, y=cy, zone=zone),
                confidence=conf,
                bbox=item.get("bbox"),
            ))

        return detections

#  Factory 

def build_detector(backend: Optional[str] = None) -> BaseDetector:
    """
    Instantiate the configured detection backend.

    backend: "yolo" | "claude" | None (reads from config)
    """
    from core.config import DETECTION_BACKEND

    backend = backend or DETECTION_BACKEND
    if backend == "yolo":
        return YoloDetector()
    elif backend == "claude":
        return ClaudeDetector()
    else:
        raise ValueError(f"Unknown detection backend: {backend!r}. Use 'yolo' or 'claude'.")