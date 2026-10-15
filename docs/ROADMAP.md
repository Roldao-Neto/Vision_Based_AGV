# Roadmap — Vision-Based AGV (odometry + obstacle avoidance)

Goal: the robot leaves **A** and reaches **B** within 5 cm, localizing **only by wheel odometry**,
detecting obstacles with the camera and replanning around them on an occupancy grid.

- 7 working days + **Day 8 as slack**. No dates on purpose.
- Each day lists **Tasks**, **README** (section to update that day), **Done when** (exit criterion) and **Record** (numbers/files to keep for the thesis).
- A day is not finished until its *Done when* holds. If a day slips, eat into Day 8, not into the next day's scope.
- Agreed design decisions are summarized in [`../CLAUDE.md`](../CLAUDE.md).

---

## Day 1 — Toolchain and wheel speed control

**Setup** (details in `docs/logs/day1-setup.md`)
- [x] Board versions checked first and updated once with `system update`: arduino-app-cli 0.13.0, arduino-router 0.10.0, `arduino:zephyr` 1.0.0. Frozen until Day 7 is done (see `CLAUDE.md`, Freezing the board's versions).
- [x] Board backed up before the first deploy (`../TCC_Artifacts/board_backup_20261010/`); the old motor demo `agv-motors-test` must not be started.
- [x] `deploy.sh`: deploy (stop, rsync, `app start`, version check, logs) and `pull <day>` (moves `/app/logs/` into `data/<day>/`, only between runs); `run <command>` came with Day 1 Firmware. See `CLAUDE.md`, Development workflow.
- [x] Per-run logs: unique names, every row flushed (`python/run_log.py`).
- [x] OpenCV 4.13.0+1ddb20b comes from the container image and stays out of `requirements.txt`.
- [x] `sketch/sketch.yaml` as App Lab generates it, plus `fqbn: arduino:zephyr:unoq`.
- [x] Patched `Arduino_RouterBridge` 0.4.3 in `sketch/libraries/` (bridge thread stack 2048 B, filled with `0xAA`); `app start` uses this copy.
- [x] Versions recorded in `docs/board-versions.txt` (`arduino_app_bricks` 0.12.0, pinned in `pyproject.toml`); `deploy.sh` compares them on every deploy.
- [x] Minimal app: `ping`, 5 Hz `hb`, handlers through the command queue (256 calls on the bridge thread and 95 on the main thread over 70 s), Bridge stack peak ~930 B with the emergency below 512 B untouched; a 32-waypoint `set_path` in integer mm (217 B) is acked and the float version (601 B) is refused by the router.
- [x] Editor support: arduino-cli 1.5.1 and `arduino:zephyr` 1.0.0 on the PC, `build/compile_commands.json`, clangd in Zed.
- [x] 20 ms tick in `loop()`: tick start 0–1.1 ms late in 99.89 % of ticks, no overrun; a large `set_path` holds `loop()` off ~35 ms, so it is sent only with the robot stopped. The tick stays in `loop()`.

**Firmware** (details in `docs/logs/day1-firmware.md`)
- [x] Sketch split into modules in `sketch/src/<module>/` (`.h` + `.cpp`, one namespace each, its state `static` in the `.cpp`); `sketch.ino` keeps only `setup()`, `loop()` and `tick()`. The board builds `src/` to the same size as the PC (107 484 B / 43 532 B) and its version lines match `docs/board-versions.txt`.
- [x] Own TB6612 driver (`motor_driver`): signed duty per wheel, coast and short brake; one `analogWrite(pin, 0)` per PWM pin, then 20 kHz with `pwm_set_cycles` (`pwm_hz` = 20000, `pwm_err` = 0 on the board). Directions set off the floor: `kLeftMotorReversed = false`, `kRightMotorReversed = true`.
- [x] x4 quadrature encoders (`CHANGE` on A and B, `INPUT_PULLUP`, a state table that counts a missed edge as an error): `kRightEncReversed = true`, so both wheels count positive forward; 0 missed edges turning by hand.
- [x] Mode `count`: 1319.7 (left) and 1319.8 (right) counts per wheel revolution, ±0.5 (3 runs of 10 turns by hand); the firmware uses 1319.75 for both until Day 2.
- [x] Wheel speed (`wheel_speed`) first in the 20 ms tick: count delta over the measured dt (18.8–21.1 ms), resolution 50 counts/s per tick.
- [x] Motion limits in firmware: every moving mode takes a time limit, plus a distance limit (the farther wheel) where it drives; out-of-range requests are refused in the handler, and the STM32 ends the mode by itself, coasting in open loop and with a ramped stop in closed loop (see `CLAUDE.md`, Bridge contract, `mode`).
- [x] Wheels off the floor for the first run of all new motor code (`pwm_set`, directions and count signs, `step`, the 2 ms sampling, `ramp`); the rule still applies to every new mode.
- [x] Mode `step` (2): duty per wheel ≤ 30 %, ≤ 1000 ms, ≤ 500 mm, coast at the end; counts sampled every 2 ms by a `k_timer` and sent as `step_samples` (15 samples, ~193 B, every 40 ms), with loss detection in Python and one CSV per step (501/501 samples off the floor, 2 ms ± 20 µs).
- [x] Mode `ramp` (3) for `pwm0`: both wheels, duty rising at 10–200 thousandths/s up to ≤ 30 % (≤ 6 s), ≤ 200 mm, one sample per tick; off-floor data shows single counts well before sustained motion, so the analysis needs a sustained-motion criterion.
- [x] Floor identification session, robot fully assembled on the arena floor, LiPo freshly charged (12.6 V): steps at ±20, ±25, ±30 % and one ramp each way, all samples complete (`results/day1/20261011-195756_app_*`).
- [x] `./deploy.sh run <command>` sends the mode commands through `cmd/`; commands left there while the app was stopped are discarded at the next start (`cmd_discarded`).

**Analysis** (details in `docs/logs/day1-analysis.md`; scripts in `analysis/`, plots in `results/day1/plots/`)
- [x] First-order model per wheel and direction, fitted on counts (`day1_identify.py`, rms 1.3–5.1 counts, τ 96–164 ms per step); `pwm0` = start of sustained motion on the ramp (5 consecutive 20 ms intervals with a count): left 7.4 % fwd / 8.8 % bwd, right 6.9 / 7.2 %; K refit through the steps with that offset: left 7160 / 6668, right 7271 / 7509 counts/s per unit duty.
- [x] Slip check: K agrees across 20, 25 and 30 %; τ falls gradually with amplitude (e.g. right fwd 128 / 103 / 96 ms), so Rolds kept every step and τ is the mean per wheel and direction (left 154 / 147, right 109 / 143 ms).
- [x] PI gains (`day1_pi.py`, `pi_gains.csv`), decided by Rolds: pole-zero cancellation with Tcl = 0.1 s, feedforward `pwm0·sign(v) + (v + τ·a_ref)/K` (see `CLAUDE.md`, Architecture), conditional integration, duty limited to 50 %. Simulated: ramp error ≤ 6 mm/s after the first 0.1 s, step 0 → 0.1 m/s with 18–21 % overshoot and 0.5–0.7 s settling, duty ≤ 0.32.
- [x] `wheel_pi` (pure C++, native tests through `uv run pytest`) and mode `speed` (4): one reference for both wheels, ramp or step; time, distance or command → ramped stop at 0.5 m/s², then coast.
- [x] Closed-loop tests on the floor, forward and backward (`day1_closed_loop.py`): ramp to 0.25 m/s at 0.5 m/s² with tracking error rms 5–6 mm/s (mostly count quantization), 100 ms-smoothed max 6.7–12.8 mm/s while ramping up and 6.0–7.4 mm/s at 0.25 m/s; step 0 → 0.1 m/s with 10–17 % overshoot, settling 280–420 ms to ±10 %; duty ≤ 0.42, never saturated; close to the simulation. Bridge stack peak 896 B (≥ 1152 B untouched), 0 overruns.
- [x] `encoder_guard` (approved by Rolds): ends `speed` at once, coasting, with reason 5 = `encoder` when a wheel is driven at |duty| ≥ 20 % for 200 ms without a count; replayed on the recorded runs it trips only on the unpowered one, and on the board with one encoder unplugged after 201 ms. The closed-loop modes of Days 2 and 3 use it too.
- [x] Extra: a 1 m closed-loop run (`speed 250 500 4500 937`, caps raised to 4500 ms and 1000 mm): 997 mm by the encoders, both wheels within one count, smoothed error ≤ 5 mm/s at 0.25 m/s.

---

## Day 2 — Straight line, odometry and calibration

**Firmware**
- [ ] Odometry at 20 ms (midpoint integration):
  `d = (dL + dR)/2`, `dθ = (dR − dL)/b`, `x += d·cos(θ + dθ/2)`, `y += d·sin(θ + dθ/2)`, `θ += dθ`.
- [ ] Heading PID with a fixed target, used for driving straight; wheel setpoints `vL = v − ω·b/2`, `vR = v + ω·b/2`.
- [ ] Calibration modes: `straight` (fixed distance), `spin` (N turns in place), `umbmark` (square path, CW or CCW). They already use the 0.5 m/s² ramp (and the angular ramp α = 2a/b, see `CLAUDE.md`, Motion), because a step to 0.25 m/s slips the wheels and corrupts mm/tick and b. Each one also has the Day 1 time limit, since its distance or turn target is measured by the encoders and a failed encoder would never reach it.

**Linux / PC**
- [ ] Python reference implementation of the odometry + pytest, fed with recorded tick logs, to cross-check the firmware.

**Bench**
- [ ] mm/tick per wheel: drive the A→B line (1.38 m) 5 times and tape-measure the real distance.
- [ ] Track width b: 5 × 360° spins in place (nominal 21.7 cm).
- [ ] UMBmark: 1 × 1 m square, 5 runs CW + 5 runs CCW → correction factors for wheel-diameter and track-width errors.

**README:** fill *Calibration* with the measured values and how each one was obtained.

**Done when:** calibrated parameters are stored in the firmware and a 1.38 m straight run ends with a measured lateral error.
**Record:** mm/tick L/R, b, UMBmark error clusters before/after correction.

---

## Day 3 — Point-to-point control, Bridge and UI: A→B without obstacles

**Firmware**
- [ ] State machine IDLE → ROTATE → DRIVE → ARRIVED with a waypoint queue (≤ 32 absolute (x, y) points).
- [ ] Trapezoidal ramps: 0.25 m/s cruise, 0.5 m/s², rotation up to 90 °/s at α = 2a/b. Below |error| = 3° the rotation ramps ω down to zero and ROTATE ends with ω = 0 (see `CLAUDE.md`, Motion).
  - The ramp uses the **along-track** remaining distance `s = (w − p)·u`, never the Euclidean distance (see `CLAUDE.md`, Motion).
- [ ] DRIVE: heading target re-aimed at the waypoint every tick; freeze it within 10 cm; go back to ROTATE if |error| > 30°.
- [ ] Stop at every waypoint (see `CLAUDE.md`, Motion):
  - the ramp reaches zero speed exactly at the waypoint;
  - below `s` = 1–2 cm (including `s < 0`) steering stops and the speed keeps ramping down; ARRIVED when the commanded and measured speeds are zero;
  - 5 cm only as a timeout fallback, logged.
- [ ] Bridge, every handler through the command queue (see `CLAUDE.md`, Bridge limits and threading):
  - `pose` notify every 2nd tick (25 Hz): `t_ms, x, y, θ, state, path_id, wp_idx`, with `t_ms` an integer;
  - `set_path(id, [x1_mm, y1_mm, …])` with ack: 1 to 32 absolute waypoints in integer mm, start not included; validate an even length from 2 to 64 and return `false` otherwise;
  - `reset_pose(x_mm, y_mm, θ_mrad)` with the axle pose as integers;
  - `stop` (ramped, 0.5 m/s²);
  - `mode` with an integer mode code and integer parameters.
- [ ] Heartbeat watchdog: no `hb` for 1 s → brake and stop (disabled in calibration modes). This is the only place, besides emergencies, where the short brake is used.

**Linux**
- [ ] Mission manager, in its own thread and the only sender of motion commands (see `CLAUDE.md`, Bridge limits and threading):
  - `reset_pose` with the start axle pose (275, 745, 0);
  - sends the path, only while the robot is stopped (see `CLAUDE.md`, Bridge limits: a 32-waypoint `set_path` holds the tick off ~35 ms while it arrives);
  - waits for ARRIVED on the last `wp_idx` of the current `path_id`.
  Bridge `call`s are never made from inside a `Bridge.provide` handler (it raises `RuntimeError`).
- [ ] Robot center ↔ axle midpoint conversion (axle is 7 cm behind the center). Everything is planned and sent in axle coordinates: the start is A − 7 cm in x; the path is planned to B, then the last waypoint is pulled back 7 cm along the last segment so the **center** ends at B.
- [ ] Clock sync: `t_ms` is the STM32 clock and is not synchronized with Linux.
  - On every `pose`, store the Linux monotonic receive time.
  - Estimate the offset as the minimum of `(receive − t_ms)` over a sliding window of ~30 s (the least-delayed recent message), and convert poses to the Linux clock.
  - Record the offset and the jitter it absorbs.
- [ ] Flask UI: Start / Stop buttons, live pose. The `flask_video_webui` brick builds its Flask app inside `start_simple_video()`, so it must be refactored to create the app in `__init__` and let `main.py` register its own routes.
- [ ] Per-run CSV logs in `/app/logs/` (poses, paths sent, events).

**README:** fill *Running a mission* (Flask UI, Bridge messages, where logs are saved).

**Done when:** A→B with the robot center reaching (1.725, 0.745) within 5 cm several times in a row, plus one hand-written multi-waypoint path.
**Record:** arrival error of each test run.

---

## Day 4 — Dataset day + offline planner

**Bench (most of the day)**
- [ ] Capture the dataset on the MDF arena with the mounted camera: all obstacle classes, 0.15–1.0 m, varied angles and positions, several lighting conditions, background-only frames.
- [ ] Before training, choose the impulse's resize mode and record it with the resulting horizontal FOV in the README. Recommended: "Fit shortest axis" for resolution, which gives ~43° instead of ~70°. See `CLAUDE.md`, Camera.
- [ ] Label and train in Edge Impulse (YOLO-Pro); export the Linux `.eim` (aarch64), put it in `models/` on the PC and `chmod +x` it.
- [ ] Smoke test of the new `.eim` inside the app container (moved here from Day 1):
  - `six` installed, `pyaudio` stubbed (see `CLAUDE.md`);
  - import, `init()`, one `classify()` on a camera frame converted BGR → RGB (see `CLAUDE.md`, Camera);
  - record the inference FPS, including the conversion and `get_features_from_image_auto_studio_settings`. This de-risks Day 5.
- [ ] Measure each obstacle class: width, depth and height.

**PC (in parallel while training runs, pytest)**
- [ ] Occupancy grid 5 cm (40 × 30 cells), in axle coordinates.
- [ ] Inflation: walls by 24.6 cm (21.6 cm rotation radius + 3 cm margin); obstacles by 24.6 cm + the circumscribed radius of the class footprint (center to farthest corner). Free axle corridor: x ∈ [0.246, 1.754], y ∈ [0.246, 1.254].
- [ ] Escape rule for replanning only: if the robot's current cell is inflated, allow crossing inflated (never raw obstacle) cells at extra cost until the first free cell; log every use. A and B are placed so the start and goal cells are always free.
- [ ] Dijkstra, 8 neighbours (diagonal cost √2), no corner cutting.
- [ ] Line-of-sight path simplification on the inflated grid.
- [ ] Detection association: same class within ~20 cm = same obstacle (average its position). The radius is a parameter, revisited on Day 5.
- [ ] "Path blocked?" check, with hysteresis:
  - plan with the full inflation (24.6 cm + footprint radius);
  - the remaining path is blocked only if it enters the inflation without the 3 cm margin (21.6 cm + footprint radius);
  - run the check for new obstacles and for position updates;
  - test that a 1–2 cm shift of a known obstacle does not trigger a replan.

**README:** start *Obstacle detection*: classes, obstacle dimensions, dataset size, model.

**Done when:** the model runs on the board and all planner tests pass.
**Record:** dataset size per class, model metrics, obstacle dimensions, inference FPS from the smoke test.

---

## Day 5 — Detector on the robot + distance calibration

**Linux**
- [ ] Rebuild the capture in `python/main.py` (the earlier version is in commit `b34ea46`) as two threads, following the frame rules in `CLAUDE.md` (the `t_ms` section):
  - capture thread: reads every frame and keeps only the latest (frame, timestamp) pair, with the V4L2 timestamp checked on the board; a failure in `cam.open()` or `cam.read()` is logged instead of silently killing the thread;
  - inference thread, on the latest pair: `pyaudio` stub, BGR → RGB, `get_features_from_image_auto_studio_settings`; map each bbox back to 1280 × 720 with the inverse of the resize mode;
  - draw bboxes on the BGR frame in the Flask stream, encoded at ~640 × 360 and ≤ 10 fps so it does not compete with inference for CPU.
- [ ] Method (b): floor homography from 8–12 tape marks measured in the robot frame (axle origin). It also gives the **bearing**, measured from the camera, used by both methods.
- [ ] Method (a): `Z = k/h` with one k per class, the depth along the optical axis, combined with the bearing as in `CLAUDE.md`, Camera. Fit k against the camera → front-face depth (axle → front face − 0.17 m).
- [ ] Obstacle position = front face F + depth/2 along the bearing, i.e. the footprint center (formulas in `CLAUDE.md`, Camera).
- [ ] Filters: drop detections beyond d_max (start at 0.7 m of depth Z), bboxes touching the image bottom (full-frame coordinates) and positions outside the arena; require 3 consecutive frames.
- [ ] `Camera.open()` only enforces focus; make it also fail when zoom (and exposure / white balance) do not stick, since a wrong zoom silently invalidates the homography and the k/h fits.

**Bench**
- [ ] Each class at 0.3–1.0 m every 10 cm, centered and to the sides → error versus distance for (a) and (b). Tape from the axle to the obstacle's front face, plus the lateral offset.
- [ ] Repeat a few points while the robot drives and brakes toward the obstacle: with the lens 5.45 cm above the floor, (b) shifts ~1.6 cm per 0.1° of pitch at 0.7 m (Z²/h), which the static bench does not show.
- [ ] Choose (a), (b) or a distance-weighted blend; confirm d_max.
- [ ] Set the association radius from the error curve (about 2–3σ at d_max) instead of the initial ~20 cm.

**README:** finish *Obstacle detection*: chosen distance method, its error curve, d_max.

**Done when:** the distance method is chosen from data and its error curve is recorded.
**Record:** error versus distance plots for both methods, final d_max, association radius, inference FPS with the final model while the capture thread and the Flask stream run (used by the Day 7 layout check).

---

## Day 6 — Full integration and replanning

- [ ] Match each frame, by its timestamp (Day 5), to the pose closest in time, using the clock offset from Day 3; transform detections robot frame → arena frame.
- [ ] Ignore detections while the pose state is ROTATE: a timing error of 30–60 ms between a frame and its pose is ~3–5° of bearing at 90 °/s (~3–7 cm at 0.7 m).
- [ ] Association → grid update → if the path is blocked (with the Day 4 hysteresis), the mission thread:
  - sends a ramped `stop` and waits for a `pose` with the robot stopped (the ramp takes ~0.5 s and ~6 cm, more than one cell);
  - replans from that pose (Dijkstra + simplification), sends the new `set_path` with a new `path_id` (only now, with the robot stopped: see `CLAUDE.md`, Bridge limits), and resumes.
  Path progress and ARRIVED from `pose` messages that still carry the old `path_id` are ignored. Their position is still used.
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

Before the runs:
- [ ] Check every S1/S2 obstacle layout with the planner on the PC (real obstacle positions + inflation) and use only layouts where:
  - a path exists (one centered obstacle already leaves only ~20 cm corridors for the axle);
  - same-class obstacles are farther apart than the association radius (closer ones merge into one obstacle);
  - every obstacle that blocks the planned or a replanned path stays inside the camera's horizontal FOV and d_max for at least 3 inference frames (at the Day 5 FPS, driving at 0.25 m/s) before the robot has to stop for it.

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
