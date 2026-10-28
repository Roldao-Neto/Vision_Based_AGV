import cv2
import numpy as np
import pytest
from flask import Flask
from mission import Mission, Pose
from webui import preview, register


class FakeCapture:
    def __init__(self):
        self.pair: tuple[np.ndarray, float] | None = None

    def latest(self):
        return self.pair


def make(capture=None):
    calls = []
    m = Mission(lambda method, *a: calls.append(method) or True, lambda n, d: None, lambda *a: None)
    app = Flask(__name__)
    register(app, m, capture or FakeCapture())  # type: ignore[arg-type]
    return app.test_client(), m, calls


def test_buttons_only_post_events():
    client, m, calls = make()
    assert client.post("/start").status_code == 204
    assert calls == []  # the mission thread sends, not Flask
    m.step()
    assert calls == ["reset_pose", "set_path"]
    assert client.post("/stop").status_code == 204
    m.step()
    assert calls[-1] == "mode"


def test_state_and_page():
    client, m, _ = make()
    st = client.get("/state").get_json()
    assert st["status"] == "idle" and st["pose"] is None
    assert st["path"] == [[0.178, 0.745]]
    assert b"<canvas" in client.get("/").data
    m.on_pose(Pose(0.0, 0, 0.0, 1.0, 0.5, 1.5707963, 2, 1, 0))
    p = client.get("/state").get_json()["pose"]
    assert (p["x"], p["y"]) == (1.0, 0.5)  # the axle
    assert (p["center_x"], p["center_y"]) == pytest.approx((1.0, 0.57))  # 7 cm ahead, facing +y


def frame():
    return np.random.default_rng(0).integers(0, 256, (720, 1280, 3), np.uint8)


def test_snapshot_is_the_exact_frame_and_counts_only_served_images():
    cap = FakeCapture()
    client, _, calls = make(cap)
    assert client.get("/snapshot.png").status_code == 503  # no frame yet: no file, no count
    assert client.get("/snapshot/next").get_json() == {"next": 1}

    f = frame()
    cap.pair = (f, 1.0)
    r = client.get("/snapshot.png")
    assert r.status_code == 200 and r.mimetype == "image/png"
    assert r.headers["Content-Disposition"] == "attachment; filename=im_1.png"
    assert r.headers["Cache-Control"] == "no-store"
    png = cv2.imdecode(np.frombuffer(r.data, np.uint8), cv2.IMREAD_UNCHANGED)
    assert png is not None and np.array_equal(png, f)  # lossless, full 1280 x 720 BGR
    assert client.get("/snapshot/next").get_json() == {"next": 2}

    # after a restart the page sends where to continue
    r = client.get("/snapshot.png?n=41")
    assert r.headers["Content-Disposition"] == "attachment; filename=im_41.png"
    assert client.get("/snapshot/next").get_json() == {"next": 42}
    assert calls == []  # never the Bridge


def test_preview_is_small_jpeg():
    cap = FakeCapture()
    cap.pair = (frame(), 1.0)
    part = next(preview(cap))  # type: ignore[arg-type]
    head, jpg = part.split(b"\r\n\r\n", 1)
    assert head == b"--frame\r\nContent-Type: image/jpeg"
    img = cv2.imdecode(np.frombuffer(jpg[:-2], np.uint8), cv2.IMREAD_COLOR)
    assert img is not None and img.shape == (360, 640, 3)
