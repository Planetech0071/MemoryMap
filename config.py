"""
MemoryMap — System Configuration
All tuneable parameters live here.
"""

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

MEMORY_FILE = DATA_DIR / "memory.json"
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Detection Backend ──────────────────────────────────────────────────────
# "yolo"   → YOLOv8 local inference (fast, offline)
# "claude" → Anthropic Vision API  (richer understanding, requires API key)
DETECTION_BACKEND: str = os.getenv("DETECTION_BACKEND", "yolo")

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

# YOLOv8 model size: n(ano) s(mall) m(edium) l(arge) x(large)
YOLO_MODEL_SIZE: str = os.getenv("YOLO_MODEL_SIZE", "n")

# ── Detection Thresholds ───────────────────────────────────────────────────
CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.50"))
# Minimum IoU overlap to consider two detections the same object
MERGE_IOU_THRESHOLD: float = float(os.getenv("MERGE_IOU_THRESHOLD", "0.40"))
# Normalised centre-distance (0-1) below which positions are "the same"
POSITION_MERGE_DISTANCE: float = float(os.getenv("POSITION_MERGE_DISTANCE", "0.12"))

# ── Camera / Video Input ───────────────────────────────────────────────────
CAMERA_SOURCE: str | int = os.getenv("CAMERA_SOURCE", "0")  # "0" → webcam
CAMERA_FPS: int = int(os.getenv("CAMERA_FPS", "5"))         # frames analysed/s
FRAME_WIDTH: int = int(os.getenv("FRAME_WIDTH", "640"))
FRAME_HEIGHT: int = int(os.getenv("FRAME_HEIGHT", "480"))

# ── Memory Behaviour ──────────────────────────────────────────────────────
# How many hours without a sighting before an object is "stale"
MEMORY_DECAY_HOURS: float = float(os.getenv("MEMORY_DECAY_HOURS", "24.0"))
# Max movement history entries kept per object
MAX_HISTORY_ENTRIES: int = int(os.getenv("MAX_HISTORY_ENTRIES", "50"))
# How often (seconds) the memory store is written to disk
PERSIST_INTERVAL_SEC: int = int(os.getenv("PERSIST_INTERVAL_SEC", "30"))

# ── Zone Detection ─────────────────────────────────────────────────────────
# Named spatial zones defined as normalised [x_min, y_min, x_max, y_max]
# Customise for your room layout.
ZONES: dict[str, list[float]] = {
    "desk":    [0.0, 0.0, 0.5, 0.5],
    "shelf":   [0.5, 0.0, 1.0, 0.5],
    "floor":   [0.0, 0.7, 1.0, 1.0],
    "general": [0.0, 0.0, 1.0, 1.0],
}

# ── API Server ─────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
API_RELOAD: bool = os.getenv("API_RELOAD", "false").lower() == "true"

# ── Query / Response ───────────────────────────────────────────────────────
# Max objects returned in "what's on my desk" type queries
MAX_QUERY_RESULTS: int = int(os.getenv("MAX_QUERY_RESULTS", "10"))
# Seconds within which an object is considered "currently visible"
CURRENT_VISIBLE_WINDOW_SEC: int = int(os.getenv("CURRENT_VISIBLE_WINDOW_SEC", "30"))
