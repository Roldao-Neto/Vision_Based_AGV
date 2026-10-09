# Roadmap — Vision-Based AGV (odometry + obstacle avoidance)

Goal: the robot leaves **A** and reaches **B** within 5 cm, localizing **only by wheel odometry**,
detecting obstacles with the camera and replanning around them on an occupancy grid.

- 7 working days + **Day 8 as slack**. No dates on purpose.
- Each day lists **Tasks**, **README** (section to update that day), **Done when** (exit criterion) and **Record** (numbers/files to keep for the thesis).
- A day is not finished until its *Done when* holds. If a day slips, eat into Day 8, not into the next day's scope.
- Agreed design decisions are summarized in [`../CLAUDE.md`](../CLAUDE.md).

---

## Day 1 — Toolchain and wheel speed control

**Setup**
- [ ] `deploy.sh`: rsync `app.yaml`, `python/`, `sketch/`, `bricks/` to the board over Wi-Fi, then `arduino-app-cli app start` and follow the logs.
- [ ] Minimal app: sketch and Python exchange a Bridge ping; Python sends the `hb` heartbeat (5 Hz).
- [ ] Editor support for the sketch:
  - install `arduino-cli` and the `arduino:zephyr` core on the PC;
  - generate `compile_commands.json` with `arduino-cli compile --only-compilation-database`;
  - point Zed's clangd at it, with `--query-driver` for `arm-zephyr-eabi-g++` in the project `.zed/settings.json`, so `Arduino.h` and the Zephyr APIs resolve.
  The current `.clangd` only makes clangd parse `.ino` as C++.
- [ ] Check whether the Zephyr core exposes `k_timer` / `k_thread` to the sketch. If not, use a `micros()`-scheduled loop and log its jitter.

**Firmware**
- [ ] Own TB6612 driver: signed PWM per wheel, explicit brake and coast. Left = D6/D7/D8, right = D9/D10/D11, STBY is hardwired to 3.3 V.
- [ ] x4 quadrature interrupts: left D2 (A) / D4 (B), right D3 (A) / D5 (B). Forward motion must count positive on both wheels.
- [ ] Mode `count`: mark the wheel, turn it 10 times by hand, read counts → **counts per wheel revolution**.
- [ ] Fixed 20 ms control tick; wheel speed from tick deltas.
- [ ] Mode `step`: apply PWM steps (e.g. 20 %, 30 %, 40 %) and stream speed to Python → CSV.

**Analysis**
- [ ] Fit a first-order model (gain K, time constant τ) per wheel from the step CSVs.
- [ ] Compute PI gains from the model; feedforward `pwm = v/K`; anti-windup.
- [ ] Closed-loop test: speed steps 0 → 0.25 m/s per wheel.

**README:** fill *Setup and running* (PC `uv sync`, `deploy.sh`, starting the app, editor setup).

**Done when:** both wheels follow a 0.25 m/s step with known overshoot and settling time.
**Record:** counts/rev, K and τ per wheel, PI gains, step response plots, loop jitter.

---

## Day 2 — Straight line, odometry and calibration

**Firmware**
- [ ] Odometry at 20 ms (midpoint integration):
  `d = (dL + dR)/2`, `dθ = (dR − dL)/b`, `x += d·cos(θ + dθ/2)`, `y += d·sin(θ + dθ/2)`, `θ += dθ`.
- [ ] Heading PID with a fixed target, used for driving straight; wheel setpoints `vL = v − ω·b/2`, `vR = v + ω·b/2`.
- [ ] Calibration modes: `straight` (fixed distance), `spin` (N turns in place), `umbmark` (square path, CW or CCW).

**Linux / PC**
- [ ] Python reference implementation of the odometry + pytest, fed with recorded tick logs, to cross-check the firmware.

**Bench**
- [ ] mm/tick per wheel: drive the A→B line (1.52 m) 5 times and tape-measure the real distance.
- [ ] Track width b: 5 × 360° spins in place (nominal 21.7 cm).
- [ ] UMBmark: 1 × 1 m square, 5 runs CW + 5 runs CCW → correction factors for wheel-diameter and track-width errors.

**README:** fill *Calibration* with the measured values and how each one was obtained.

**Done when:** calibrated parameters are stored in the firmware and a 1.52 m straight run ends with a measured lateral error.
**Record:** mm/tick L/R, b, UMBmark error clusters before/after correction.

---

## Day 3 — Point-to-point control, Bridge and UI: A→B without obstacles

**Firmware**
- [ ] State machine IDLE → ROTATE → DRIVE → ARRIVED with a waypoint queue (≤ 32 absolute (x, y) points).
- [ ] Trapezoidal ramps: 0.25 m/s cruise, 0.5 m/s², rotation up to 90 °/s; rotation ends at |error| < 3°.
- [ ] DRIVE: heading target re-aimed at the waypoint every tick; freeze it within 10 cm; go back to ROTATE if |error| > 30°.
- [ ] Arrival tolerance 5 cm at every waypoint (stop at each one).
- [ ] Bridge: `pose` notify at 20 Hz (`t_ms, x, y, θ, state`), `set_path(id, [x1, y1, …])` with ack, `stop`, `mode`.
- [ ] Heartbeat watchdog: no `hb` for 1 s → brake and stop (disabled in calibration modes).

**Linux**
- [ ] Mission manager: resets odometry at A, sends the path, waits for ARRIVED.
- [ ] Robot center ↔ axle midpoint conversion (axle is 7 cm behind the center); goal B is converted using the last segment direction.
- [ ] Clock sync: `t_ms` is the STM32 clock and is not synchronized with Linux. On every `pose`, store the Linux monotonic receive time; estimate the offset as the minimum of `(receive − t_ms)` (the least-delayed message) and convert poses to the Linux clock. Record the offset and the jitter it absorbs.
- [ ] Flask UI: Start / Stop buttons, live pose. The `flask_video_webui` brick builds its Flask app inside `start_simple_video()`, so it must be refactored to create the app in `__init__` and let `main.py` register its own routes.
- [ ] Per-run CSV logs (poses, paths sent, events).

**README:** fill *Running a mission* (Flask UI, Bridge messages, where logs are saved).

**Done when:** A→B with the robot center reaching (1.77, 0.745) within 5 cm several times in a row, plus one hand-written multi-waypoint path.
**Record:** arrival error of each test run.

---

## Day 4 — Dataset day + offline planner

**Bench (most of the day)**
- [ ] Capture the dataset on the MDF arena with the mounted camera: all obstacle classes, 0.15–1.0 m, varied angles and positions, several lighting conditions, background-only frames.
- [ ] Label and train in Edge Impulse (YOLO-Pro); export the Linux `.eim`.
- [ ] Measure each obstacle class: width, depth and height.

**PC (in parallel while training runs, pytest)**
- [ ] Occupancy grid 5 cm (40 × 30 cells).
- [ ] Inflation: walls by 15 cm; obstacles by 24.6 cm (21.6 cm rotation radius + 3 cm margin) + class half-size.
- [ ] Dijkstra, 8 neighbours (diagonal cost √2), no corner cutting.
- [ ] Line-of-sight path simplification on the inflated grid.
- [ ] Detection association: same class within ~20 cm = same obstacle (average its position).
- [ ] "Path blocked?" check: does a new inflated obstacle intersect the remaining path?

**README:** start *Obstacle detection*: classes, obstacle dimensions, dataset size, model.

**Done when:** the model runs on the board and all planner tests pass.
**Record:** dataset size per class, model metrics, obstacle dimensions.

---

## Day 5 — Detector on the robot + distance calibration

**Linux**
- [ ] Run the `.eim` in the capture loop of `python/main.py`; draw bboxes in the Flask stream.
- [ ] Method (b): floor homography from 8–12 tape marks measured in the robot frame (axle origin).
- [ ] Method (a): `d = k/h` with one k per class.
- [ ] Filters: drop detections beyond d_max (start at 0.7 m) and bboxes touching the image bottom; require 3 consecutive frames.

**Bench**
- [ ] Each class at 0.3–1.0 m every 10 cm, centered and to the sides → error versus distance for (a) and (b).
- [ ] Choose (a), (b) or a distance-weighted blend; confirm d_max.

**README:** finish *Obstacle detection*: chosen distance method, its error curve, d_max.

**Done when:** the distance method is chosen from data and its error curve is recorded.
**Record:** error versus distance plots for both methods, final d_max.

---

## Day 6 — Full integration and replanning

- [ ] Timestamp each frame right after `Camera.read()` (Linux monotonic clock) and match it to the pose closest in time, using the clock offset from Day 3; transform detections robot frame → arena frame.
- [ ] Association → grid update → if the path is blocked: stop, replan (Dijkstra + simplification), send the new `set_path`, resume.
- [ ] Flask: draw grid, inflated obstacles, current path and pose.
- [ ] Log detections (bbox, class, distance by (a) and (b)), obstacle list, every replan.
- [ ] Debug on an S1 layout, then on S2 layouts.

**README:** add known limitations found during integration; update **Status**.

**Done when:** S1 and at least one S2 layout succeed end-to-end.
**Record:** problems found and fixes (for the thesis "limitations" section).

---

## Day 7 — Experiments

Scenarios, 10 runs each:
- **S0:** no obstacles.
- **S1:** one obstacle on the A→B line.
- **S2:** 2–3 obstacles that force a detour.

Per run:
- [ ] Tape-measure both rear corners of the robot → real pose (x, y, θ) → real center.
- [ ] Arrival error (real center versus B) and odometry error (real pose versus reported pose).
- [ ] Success: center within 5 cm of B and no contact with any obstacle.
- [ ] Detection distance per obstacle, number of replans, total time.
- [ ] Pull the logs to the PC; build tables and plots.

**README:** fill *Results* (S0–S2 table and plots); set **Status** to final.

**Done when:** 30 runs are logged and summarized.

---

## Day 8 — Slack

Reserved for slips. Only if everything is done:
- Swap Dijkstra for A* and compare.
- PyTorch detector instead of Edge Impulse.
