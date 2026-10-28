import numpy as np
from capture import Capture


class FakeCamera:
    def __init__(self, frames=0, open_error=None):
        self.frames, self.open_error, self.released = frames, open_error, False

    def open(self):
        if self.open_error:
            raise RuntimeError(self.open_error)

    def read(self):
        if self.frames == 0:
            raise RuntimeError("[Camera] Failed to read frame")
        self.frames -= 1
        return np.full((720, 1280, 3), self.frames, np.uint8), 100.0 - self.frames

    def release(self):
        self.released = True


def run(camera):
    events = []
    c = Capture(camera, lambda n, d: events.append((n, d)))  # type: ignore[arg-type]
    c.run()  # on this thread: returns when the camera fails
    return c, events


def test_keeps_latest_pair_and_logs_read_failure():
    cam = FakeCamera(frames=3)
    c, events = run(cam)
    latest = c.latest()
    assert latest is not None
    frame, t = latest
    assert t == 100.0 and frame[0, 0, 0] == 0  # the last frame read, with its stamp
    assert events == [("camera_open", ""), ("camera_error", "read: [Camera] Failed to read frame")]
    assert cam.released


def test_logs_open_failure():
    c, events = run(FakeCamera(open_error="[Camera] Failed to open camera"))
    assert c.latest() is None
    assert events == [("camera_error", "open: [Camera] Failed to open camera")]
