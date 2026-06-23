"""
MemoryMap — Engine
The central orchestrator that runs the perception-memory-query loop.

Lifecycle:
  engine = MemoryMapEngine()
  engine.start()           # starts background camera loop
  engine.ask("Where are my keys?")
  engine.stop()

Can also be used in one-shot mode (observe a single frame):
  engine.observe_frame(frame)
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional, Union
from pathlib import Path

import numpy as np
from loguru import logger

from core.config import DETECTION_BACKEND
from memory.store import MemoryStore
from query.handler import QueryHandler
from query.responder import format_response
from vision.detector import BaseDetector, build_detector
from vision.frame_reader import FrameReader


class MemoryMapEngine:
    """
    The beating heart of MemoryMap.

    Responsibilities:
      - Hold references to the detector, memory store, and query system
      - Run the continuous observe→detect→store loop in a background thread
      - Expose a simple ask(query) interface for user queries
    """

    def __init__(
        self,
        source: Union[int, str, Path] = 0,
        backend: Optional[str] = None,
        detector: Optional[BaseDetector] = None,
        store: Optional[MemoryStore] = None,
    ) -> None:
        self.source = source
        self._backend = backend or DETECTION_BACKEND

        # Core components
        self._detector: BaseDetector = detector or build_detector(self._backend)
        self._store: MemoryStore = store or MemoryStore()
        self._query_handler = QueryHandler(self._store)

        # Camera loop state
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False

        # Stats
        self._frames_processed = 0
        self._started_at: Optional[datetime] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self, phone_stream: bool = False) -> None:
        """Start the memory store and the background camera observation loop."""
        if self._is_running:
            logger.warning("Engine already running.")
            return

        self._store.start()
        self._stop_event.clear()
        self._started_at = datetime.now()
        self._is_running = True

        self._loop_thread = threading.Thread(
            target=self._observation_loop,
            daemon=True,
            name="memorymap-engine",
        )
        self._loop_thread.start()
        logger.info(
            "MemoryMap engine started (source={}, backend={}).",
            self.source, self._backend,
        )

    def stop(self) -> None:
        """Gracefully stop the observation loop and persist memory."""
        if not self._is_running:
            return

        self._stop_event.set()

        if self._loop_thread:
            self._loop_thread.join(timeout=10)

        self._store.stop()
        self._is_running = False
        logger.info(
            "MemoryMap engine stopped. Frames processed: {}.",
            self._frames_processed,
        )

    # ── Single-frame observation (API / test mode) ─────────────────────────

    def observe_frame(self, frame: np.ndarray) -> int:
        """
        Run detection on a single frame and update memory.
        Returns number of detections found.
        """
        now = datetime.now()
        detections = self._detector.detect(frame)
        self._store.ingest(detections, now)
        self._frames_processed += 1

        logger.debug(
            "Frame {}: {} detection(s).",
            self._frames_processed, len(detections),
        )
        return len(detections)

    # ── Query interface ───────────────────────────────────────────────────

    def ask(self, query: str) -> str:
        """
        Answer a natural language query about object locations.

        Returns a short, direct response string.
        """
        result = self._query_handler.handle(query)
        response = format_response(result)
        logger.info("Query: {!r} → {!r}", query, response)
        return response

    # ── Memory access ─────────────────────────────────────────────────────

    @property
    def store(self) -> MemoryStore:
        return self._store

    def status(self) -> dict:
        """Return a status dict suitable for the /status API endpoint."""
        return {
            "running": self._is_running,
            "backend": self._backend,
            "source": str(self.source),
            "frames_processed": self._frames_processed,
            "object_count": self._store.object_count(),
            "started_at": self._started_at.isoformat() if self._started_at else None,
        }

    # ── Private ────────────────────────────────────────────────────────────

    def _observation_loop(self) -> None:
        """Background thread: continuously reads frames and updates memory."""
        try:
            with FrameReader(source=self.source) as reader:
                for frame in reader.stream():
                    if self._stop_event.is_set():
                        break
                    self.observe_frame(frame)
        except Exception as exc:
            logger.error("Observation loop crashed: {}", exc)
            self._is_running = False
