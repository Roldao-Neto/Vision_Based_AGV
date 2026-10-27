"""The mission page: Start / Stop buttons and the live pose on the arena.

Routes only read the mission's snapshot or post an event to it; they never call the Bridge.
"""

from flask import Flask, jsonify
from mission import Mission

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
</style>
</head>
<body>
<h1>AGV mission: A &rarr; B</h1>
<button id="start">Start</button><button id="stop">Stop</button>
<canvas id="arena" width="800" height="600"></canvas>
<pre id="info">waiting for the first pose...</pre>
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
</script>
</body>
</html>
"""


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
