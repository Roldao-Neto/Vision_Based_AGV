import os

import cv2


class Camera:
    """Logitech C920 at 1280x720 MJPG.

    Changing the resolution invalidates the floor homography and the per-class k/h
    distance fits.
    """

    def __init__(self, device=None, width=1280, height=720):
        self._device = device or os.environ.get(
            "VIDEO_DEVICE", "/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920-video-index0"
        )
        self._width, self._height = width, height
        self._cap = None

    def open(self):
        self._cap = cv2.VideoCapture(self._device, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            raise RuntimeError("[Camera] Failed to open camera")

        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*'MJPG'))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if (w, h) != (self._width, self._height):
            self.release()
            raise RuntimeError(
                f"[Camera] asked {self._width}x{self._height}, got {w}x{h}")

    def read(self):
        """(frame, t): t is the V4L2 buffer time in s, CLOCK_MONOTONIC for a UVC camera
        (the clock of time.monotonic()), taken when the frame starts arriving."""
        if self._cap is None:
            raise RuntimeError("[Camera] Camera is not opened")
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("[Camera] Failed to read frame")
        return frame, self._cap.get(cv2.CAP_PROP_POS_MSEC) / 1000

    def release(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
