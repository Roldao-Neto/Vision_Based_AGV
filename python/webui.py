"""The mission page: Start / Stop buttons, the live pose on the arena and the camera preview.

Routes only read the mission's snapshot or the latest camera frame, or post an event to the
mission; they never call the Bridge.

The Capture button and /snapshot.png are only for the Day 4 dataset, never used during a
run, and are removed later.
"""

import time
from collections.abc import Iterator

import cv2
from capture import Capture
from flask import Flask, Response, jsonify, request
from mission import Mission

PREVIEW_SIZE = (640, 360)
PREVIEW_PERIOD_S = 0.1  # at most 10 fps, so the preview takes little CPU

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AGV mission</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 16px; background: #f6f6f4; color: #222; }
  button { font-size: 1.1rem; padding: 0.5rem 1.5rem; margin-right: 0.5rem; }
  #start { background: #2e7d32; color: white; border: 0; }
  #stop { background: #c62828; color: white; border: 0; }
  canvas { width: 100%; max-width: 800px; background: white; border: 1px solid #999; display: block; margin-top: 1rem; }
  pre { font-size: 0.95rem; }
  #preview { width: 100%; max-width: 640px; aspect-ratio: 16 / 9; background: #333; display: block; margin-top: 1rem; }
  #n { width: 5rem; font-size: 1.1rem; }
</style>
</head>
<body>
<h1>AGV mission: A &rarr; B</h1>
<button id="start">Start</button><button id="stop">Stop</button>
<canvas id="arena" width="800" height="600"></canvas>
<pre id="info">waiting for the first pose...</pre>
<h2>Camera</h2>
<img id="preview" src="/video_feed" alt="camera preview">
<p><button id="capture">Capture</button> next: im_<input id="n" type="number" min="1" value="1">.png</p>
<pre id="shot"></pre>
<script>
const W = 2.0, H = 1.5;
const STATES = ["IDLE", "ROTATE", "DRIVE", "ARRIVED"];
const cv = document.getElementById("arena"), ctx = cv.getContext("2d");
const s = cv.width / W;
const px = (x, y) => [x * s, cv.height - y * s];  // arena frame: y up

function post(url) { fetch(url, {method: "POST"}).then(refresh); }
document.getElementById("start").onclick = () => post("/start");
document.getElementById("stop").onclick = () => post("/stop");

function dot(x, y, r, color) {
  const [u, v] = px(x, y);
  ctx.fillStyle = color; ctx.beginPath(); ctx.arc(u, v, r, 0, 2 * Math.PI); ctx.fill();
}

function draw(st) {
  ctx.clearRect(0, 0, cv.width, cv.height);
  dot(0.248, 0.745, 6, "#1565c0");   // A (center)
  dot(1.651, 0.745, 6, "#2e7d32");   // B (center)
  if (st.path.length > 1) {
    ctx.strokeStyle = "#999"; ctx.setLineDash([6, 4]); ctx.beginPath();
    st.path.forEach(([x, y], i) => { const [u, v] = px(x, y); i ? ctx.lineTo(u, v) : ctx.moveTo(u, v); });
    ctx.stroke(); ctx.setLineDash([]);
  }
  const p = st.pose;
  if (!p) return;
  // Body 22 x 24 cm around the center (from arena.axle_to_center, 7 cm ahead of the axle)
  const [u, v] = px(p.center_x, p.center_y);
  ctx.save(); ctx.translate(u, v); ctx.rotate(-p.theta);
  ctx.fillStyle = "rgba(255, 143, 0, 0.5)"; ctx.fillRect(-0.12 * s, -0.11 * s, 0.24 * s, 0.22 * s);
  ctx.strokeStyle = "#e65100"; ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0.15 * s, 0); ctx.stroke();
  ctx.restore();
  dot(p.x, p.y, 3, "#000");          // axle
}

function refresh() {
  fetch("/state").then(r => r.json()).then(st => {
    draw(st);
    const p = st.pose;
    document.getElementById("info").textContent =
      `mission: ${st.status}   path_id: ${st.path_id}\\n` + (p ?
      `axle: x=${p.x.toFixed(3)} m  y=${p.y.toFixed(3)} m  theta=${(p.theta * 180 / Math.PI).toFixed(1)} deg\\n` +
      `state: ${STATES[p.state] ?? p.state}  path_id: ${p.path_id}  wp_idx: ${p.wp_idx}  age: ${p.age_s.toFixed(2)} s`
      : "no pose yet");
  }).catch(() => {});
}
setInterval(refresh, 200);
refresh();

// Dataset capture (Day 4): the full 1280 x 720 frame as PNG, downloaded as im_N.png
const nIn = document.getElementById("n"), shot = document.getElementById("shot");
fetch("/snapshot/next").then(r => r.json()).then(j => { nIn.value = j.next; }).catch(() => {});
document.getElementById("capture").onclick = async (ev) => {
  const btn = ev.target, n = parseInt(nIn.value);
  btn.disabled = true;
  try {
    const r = await fetch(`/snapshot.png?n=${n}`, {cache: "no-store"});
    if (!r.ok) { shot.textContent = `capture failed: ${r.status} ${await r.text()}`; return; }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await r.blob());
    a.download = `im_${n}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    nIn.value = n + 1;
    shot.textContent = `saved im_${n}.png`;
  } catch (e) {
    shot.textContent = `capture failed: ${e}`;
  } finally {
    btn.disabled = false;
  }
};
</script>
</body>
</html>
"""


def preview(capture: Capture) -> Iterator[bytes]:
    """MJPEG parts of the latest frame at 640 x 360, for Server.video."""
    while True:
        time.sleep(PREVIEW_PERIOD_S)
        latest = capture.latest()
        if latest is None:
            continue
        small = cv2.resize(latest[0], PREVIEW_SIZE, interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"


def register(app: Flask, mission: Mission, capture: Capture) -> None:
    app.add_url_rule("/", "index", lambda: PAGE)
    app.add_url_rule("/state", "state", lambda: jsonify(mission.snapshot()))

    def start():
        mission.post("start")
        return ("", 204)

    def stop():
        mission.post("abort")
        return ("", 204)

    app.add_url_rule("/start", "start", start, methods=["POST"])
    app.add_url_rule("/stop", "stop", stop, methods=["POST"])

    next_n = 1  # in memory: after an app restart the page sets where to continue

    def snapshot():
        """The latest full frame as PNG (lossless: exactly the decoded frame inference sees),
        as a download named im_N.png; N is ?n= from the page, or the board's count."""
        nonlocal next_n
        latest = capture.latest()
        if latest is None:
            return ("no camera frame yet", 503)
        ok, png = cv2.imencode(".png", latest[0])
        if not ok:
            return ("PNG encoding failed", 500)
        n = request.args.get("n", next_n, type=int)
        next_n = n + 1
        return Response(png.tobytes(), mimetype="image/png", headers={
            "Content-Disposition": f"attachment; filename=im_{n}.png",
            "Cache-Control": "no-store",
        })

    app.add_url_rule("/snapshot.png", "snapshot", snapshot)
    app.add_url_rule("/snapshot/next", "snapshot_next", lambda: jsonify(next=next_n))
