"""The mission page: Start / Stop buttons, the live pose on the arena with the planner's grid
and obstacles, and the camera preview with the detector's boxes.

Routes only read the mission's snapshot or the latest camera frame, or post an event to the
mission; they never call the Bridge.
"""

import time
from collections.abc import Iterator

import cv2
from capture import Capture
from detector import Detector
from flask import Flask, jsonify
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
  .row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-start; margin-top: 1rem; }
  .row > div { flex: 1 1 400px; min-width: 0; }
  canvas { width: 100%; max-width: 800px; background: white; border: 1px solid #999; display: block; }
  pre { font-size: 0.95rem; }
  #preview { width: 100%; max-width: 800px; aspect-ratio: 16 / 9; background: #333; display: block; }
</style>
</head>
<body>
<h1>AGV mission: A &rarr; B</h1>
<button id="start">Start</button><button id="stop">Stop</button>
<div class="row">
<div>
<canvas id="arena" width="800" height="600"></canvas>
<pre id="info">waiting for the first pose...</pre>
</div>
<div>
<img id="preview" src="/video_feed" alt="camera preview">
</div>
</div>
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

function circle(x, y, r, color, dash) {
  const [u, v] = px(x, y);
  ctx.strokeStyle = color; ctx.setLineDash(dash); ctx.beginPath(); ctx.arc(u, v, r * s, 0, 2 * Math.PI);
  ctx.stroke(); ctx.setLineDash([]);
}

// Planner grid (axle coordinates): occupied cells shaded, then the cell lines
function drawGrid(st) {
  const c = st.cell * s;
  ctx.fillStyle = "#ddd";
  st.grid.forEach((row, iy) => [...row].forEach((ch, ix) => {
    if (ch === "#") { const [u, v] = px(ix * st.cell, (iy + 1) * st.cell); ctx.fillRect(u, v, c, c); }
  }));
  ctx.strokeStyle = "rgba(0, 0, 0, 0.08)"; ctx.beginPath();
  for (let u = 0; u <= cv.width; u += c) { ctx.moveTo(u, 0); ctx.lineTo(u, cv.height); }
  for (let v = cv.height; v >= 0; v -= c) { ctx.moveTo(0, v); ctx.lineTo(cv.width, v); }
  ctx.stroke();
  st.obstacles.forEach(o => {
    circle(o.x, o.y, o.r_plan, "#c62828", [4, 4]);  // planning inflation
    circle(o.x, o.y, o.r_block, "#c62828", []);     // blocked check, without the margin
    dot(o.x, o.y, 4, "#c62828");
  });
}

function draw(st) {
  ctx.clearRect(0, 0, cv.width, cv.height);
  drawGrid(st);
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
</script>
</body>
</html>
"""


def preview(capture: Capture, detector: Detector) -> Iterator[bytes]:
    """MJPEG parts of the latest frame at 640 x 360 with the detections, for Server.video."""
    while True:
        time.sleep(PREVIEW_PERIOD_S)
        latest = capture.latest()
        if latest is None:
            continue
        small = cv2.resize(latest[0], PREVIEW_SIZE, interpolation=cv2.INTER_AREA)
        s = PREVIEW_SIZE[0] / 1280
        for b in detector.boxes():
            p0, p1 = (round(b.x0 * s), round(b.y0 * s)), (round(b.x1 * s), round(b.y1 * s))
            cv2.rectangle(small, p0, p1, (0, 0, 255), 2)
            cv2.putText(small, f"{b.label} {b.score:.2f}", (p0[0], max(p0[1] - 5, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"


def register(app: Flask, mission: Mission) -> None:
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
