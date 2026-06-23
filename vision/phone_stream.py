"""
MemoryMap — Phone Stream Server
Allows streaming frames from a phone camera over WebSocket.
"""

from __future__ import annotations

import base64
import threading
import time
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from loguru import logger

from core.engine import MemoryMapEngine


class PhoneStreamServer:
    """
    WebSocket server for receiving frames from a phone camera.
    """

    def __init__(self, engine: MemoryMapEngine, port: int = 9000) -> None:
        self.engine = engine
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def run_in_thread(self) -> None:
        """Start the phone stream server in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Phone stream server started on port {}", self.port)

    def stop(self) -> None:
        """Stop the phone stream server."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """Run the WebSocket server (placeholder)."""
        # This is a placeholder implementation
        # In production, you'd use FastAPI WebSocket or similar
        while not self._stop_event.is_set():
            time.sleep(1)
