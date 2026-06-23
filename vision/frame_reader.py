"""
MemoryMap — Frame Reader
Abstracts camera and video-file input into a uniform iterator of frames.

Supports:
  - Webcam (integer device id, e.g. 0)
  - Video file (file path)
  - Single image (for testing / still-frame mode)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Generator, Optional, Union

import cv2
import numpy as np
from loguru import logger

from core.config import CAMERA_FPS, FRAME_HEIGHT, FRAME_WIDTH


class FrameReader:
    """
    Yields numpy BGR frames from a camera or video file at a controlled rate.

    Usage:
        reader = FrameReader(source=0, fps=5)
        for frame in reader.stream():
            process(frame)
    """

    def __init__(
        self,
        source: Union[int, str, Path] = 0,
        fps: int = CAMERA_FPS,
        width: int = FRAME_WIDTH,
        height: int = FRAME_HEIGHT,
    ) -> None:
        # Normalise source
        if isinstance(source, str) and source.isdigit():
            self.source: Union[int, str] = int(source)
        elif isinstance(source, Path):
            self.source = str(source)
        else:
            self.source = source
        self.fps = max(1, fps)
        self.width = width
        self.height = height
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_interval = 1.0 / self.fps

    # ── Context manager ────────────────────────────────────────────────────

    def __enter__(self) -> "FrameReader":
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def open(self) -> None:
        if self._cap is not None:
            return
        self._cap = cv2.VideoCapture(self.source)

        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open video source: {self.source!r}")

        # Request resolution (camera may ignore for video files)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(
            "Video source opened: {} @ {}x{} (target FPS: {})",
            self.source, actual_w, actual_h, self.fps,
        )

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Video source closed.")

    # ── Streaming ──────────────────────────────────────────────────────────

    def stream(self) -> Generator[np.ndarray, None, None]:
        """
        Yields frames at the configured FPS.
        For video files, respects the original timing.
        Blocks are inserted to maintain the target rate.
        """
        self.open()
        assert self._cap is not None
        last_yield_time = 0.0

        while True:
            ret, frame = self._cap.read()

            if not ret:
                # Video file ended — rewind or stop
                if isinstance(self.source, str) and Path(self.source).is_file():
                    logger.info("Video file ended, stopping stream.")
                    break
                # Camera read failure — retry briefly
                logger.warning("Camera read failed, retrying")
                time.sleep(0.1)
                continue

            # Rate limiting: skip frames that arrive faster than target FPS
            now = time.monotonic()
            if (now - last_yield_time) < self._frame_interval:
                continue
            last_yield_time = now
            yield frame

    def read_one(self) -> Optional[np.ndarray]:
        """Read a single frame (useful for single-image or on-demand use)."""
        self.open()
        assert self._cap is not None
        ret, frame = self._cap.read()
        return frame if ret else None

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()


class ImageFrameReader:
    """
    Returns a single static frame from a file.
    Useful for testing and single-image mode.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

    def stream(self) -> Generator[np.ndarray, None, None]:
        frame = cv2.imread(str(self.path))
        if frame is None:
            raise RuntimeError(f"Failed to load image: {self.path}")
        yield frame  # Single frame
