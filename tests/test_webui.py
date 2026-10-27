import pytest
from flask import Flask
from mission import Mission, Pose
from webui import register


def make():
    calls = []
    m = Mission(lambda method, *a: calls.append(method) or True, lambda n, d: None, lambda *a: None)
    app = Flask(__name__)
    register(app, m)
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
