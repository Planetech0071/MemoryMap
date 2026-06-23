# 🧠 MemoryMap

> A second brain for physical space.

MemoryMap is a persistent spatial memory system that uses a camera feed to track objects in your environment over time. Ask it where your keys are. Ask what you left on your desk. It remembers.

---

## Architecture Overview

```
memorymap/
├── core/               # Orchestration & main loop
│   ├── engine.py       # Central MemoryMap engine
│   └── config.py       # System configuration
├── memory/             # Persistent spatial memory
│   ├── store.py        # In-memory + disk-backed object store
│   ├── object_record.py # ObjectRecord dataclass
│   └── merge.py        # Duplicate detection & merging
├── vision/             # Visual understanding
│   ├── detector.py     # Object detection (YOLOv8 or Claude Vision)
│   ├── tracker.py      # Cross-frame object tracking
│   └── frame_reader.py # Camera / video input
├── query/              # Natural language query system
│   ├── handler.py      # Query parsing + memory retrieval
│   └── responder.py    # Response formatting
├── api/                # FastAPI REST + WebSocket interface
│   ├── server.py
│   └── routes.py
├── utils/
│   ├── logger.py
│   └── time_utils.py
├── tests/
│   ├── test_memory.py
│   ├── test_query.py
│   └── test_merge.py
├── data/
│   └── memory.json     # Persisted memory store
├── main.py             # Entry point
├── requirements.txt
└── README.md
```

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run with a webcam (default device 0)
python main.py --source 0

# Run with a video file
python main.py --source /path/to/video.mp4

# Run API server only (no camera)
python main.py --api-only

# Ask a question via CLI
python main.py --query "Where are my keys?"
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | System health + object count |
| GET | `/objects` | All objects in memory |
| GET | `/objects/{name}` | Find a specific object |
| POST | `/query` | Natural language query |
| POST | `/observe` | Submit a frame (base64 JPEG) |
| DELETE | `/memory` | Clear all memory |
| WS | `/ws/live` | Live object feed (WebSocket) |

---

## Design Principles

- **Memory over detection** — consistency matters more than speed
- **Time-awareness** — all records carry timestamps; recency wins
- **Honest uncertainty** — if unsure, say so and report last known location
- **Merge, don't duplicate** — same object seen twice = one record updated
- **Modular backends** — swap YOLOv8 for Claude Vision with one config flag

---

## Configuration (`core/config.py`)

Key settings:

| Key | Default | Description |
|-----|---------|-------------|
| `DETECTION_BACKEND` | `"yolo"` | `"yolo"` or `"claude"` |
| `CONFIDENCE_THRESHOLD` | `0.5` | Min detection confidence |
| `MEMORY_DECAY_HOURS` | `24` | Hours before unseen = stale |
| `MERGE_IOU_THRESHOLD` | `0.4` | Spatial overlap for merge |
| `PERSIST_INTERVAL_SEC` | `30` | How often to save memory.json |
| `CAMERA_FPS` | `5` | Frames to process per second |

---

## Memory Record Schema

```json
{
  "id": "uuid4",
  "label": "headphones",
  "location": {"x": 0.42, "y": 0.61, "zone": "desk"},
  "first_seen": "2026-06-01T09:12:00",
  "last_seen": "2026-06-01T11:45:22",
  "confidence": 0.87,
  "observation_count": 14,
  "history": [
    {"time": "2026-06-01T09:12:00", "location": {"x": 0.42, "y": 0.61}},
    {"time": "2026-06-01T10:30:00", "location": {"x": 0.55, "y": 0.70}}
  ]
}
```

---

## Example Queries

```
"Where are my headphones?"
→ "Your headphones were last seen on the desk 23 minutes ago."

"What's on my desk right now?"
→ "Currently visible on the desk: laptop, coffee mug, notebook."

"Did I move my keys today?"
→ "Yes. Your keys were near the door at 08:14, then moved to the desk at 12:03."

"I can't find my wallet."
→ "Wallet not in current view. Last recorded location: bedroom shelf, 3 hours ago."
```

## AI Usage
```
CHATGPT and CLAUDE for brainstorming and very short debug sessions
GEMINI for cover image
V0 for the help with frontend DEMO version.
