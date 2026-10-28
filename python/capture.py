"""The capture thread: reads every camera frame and keeps only the latest (frame, t) pair.

Readers (the web preview and snapshot now, inference on Day 5) take that pair and never
wait for the camera, so a frame is never older than its stamp. A failure in open() or
read() is logged as a camera_error event and ends the thread.
"""

import threading
from collections.abc import Callable

import numpy as np
from opencv_camera_handler import Camera


class Capture:
    def __init__(self, camera: Camera, event: Callable[[str, object], None]):
        self._camera = camera
        self._event = event
        self._latest: tuple[np.ndarray, float] | None = None

    def latest(self) -> tuple[np.ndarray, float] | None:
        """The latest (frame, t), or None before the first frame. The frame is BGR and
        must not be modified: every read() returns a new array (OpenCV cap_v4l.cpp copies
        into the caller's output), so a reader holds it as long as it likes."""
        return self._latest

    def run(self) -> None:
        try:
            self._camera.open()
        except Exception as e:  # noqa: BLE001
            self._event("camera_error", f"open: {e}")
            return
        self._event("camera_open", "")
        try:
            while True:
                self._latest = self._camera.read()
        except Exception as e:  # noqa: BLE001
            self._event("camera_error", f"read: {e}")
        finally:
            self._camera.release()

    def start(self) -> None:
        threading.Thread(target=self.run, name="capture", daemon=True).start()
