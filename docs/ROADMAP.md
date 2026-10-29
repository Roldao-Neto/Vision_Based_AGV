# Roadmap — Vision-Based AGV (odometry + obstacle avoidance)

Goal: the robot leaves **A** and reaches **B** within 5 cm, localizing **only by wheel odometry**,
detecting obstacles with the camera and replanning around them on an occupancy grid.

- 7 working days + **Day 8 as slack**. No dates on purpose.
- Each day lists **Tasks**, **README** (section to update that day), **Done when** (exit criterion) and **Record** (numbers/files to keep for the thesis).
- A day is not finished until its *Done when* holds. If a day slips, eat into Day 8, not into the next day's scope.
- Agreed design decisions are summarized in [`../CLAUDE.md`](../CLAUDE.md).

### Experiments for the thesis

Every measurement the thesis reports, with its repetitions. The details are in each day.

| Day | Experiment | Repetitions | Measured | Status |
|---|---|---|---|---|
| 1 | Wheel identification (open loop) | 6 steps (±20, ±25, ±30 %) + 2 ramps | K, τ, `pwm0` per wheel and direction | done |
| 1 | Wheel speed loop (closed loop) | ramp and step, forward and backward | tracking error, overshoot, settling | done |
| 2 | Odometry cross-check, firmware vs Python | every calibration run | end-pose difference | done: every run, off the floor and on it, within 1 µm and 1 µrad |
| 2 | Straight runs **before** calibration (nominal constants) | 5 × A→B | along-line, lateral and heading error | done |
| 2 | Scale (Es) correction | from those 5 runs | mean m/count | done |
| 2 | UMBmark **before** (Es corrected) | 5 CW + 5 CCW | error clusters, E_max,syst | done |
| 2 | Ed and Eb correction (Borenstein) | from those 10 runs | m/count per wheel, b | done |
| 2 | **After** calibration | 5 × A→B + 5 CW + 5 CCW UMBmark | the same | done |
| 3 | A→B without obstacles | 5 in a row, then one multi-waypoint path 3 times | pass/fail: P stops inside a 5 cm circle around B_ref (the arrival error is measured on Day 7, S0) | done: 5/5 and 3/3 pass (sent with `./deploy.sh run`; they count, decided by Rolds) |
| 5 | Distance methods (a) k/h and (b) homography | per class: 0.3–1.0 m every 0.1 m, centered and to each side, 20 detections per position | error versus distance | |
| 5 | Distance while driving and braking | 5 approaches per class | error versus the static curve | |
| 7 | S0 / S1 / S2 missions | 10 each | success, arrival error, detection distance, replans, time | |

Every real pose is measured the same way: from a tape cross on the floor (a line along x and its perpendicular), the robot's reference point (along and across the line) and a front point on its centreline (across the line) → reference point and heading (see Day 2, Bench).

---

## Day 1 — Toolchain and wheel speed control

**Setup** (details in `docs/logs/day1-setup.md`)
- [x] Board versions checked first and updated once with `system update`: arduino-app-cli 0.13.0, arduino-router 0.10.0, `arduino:zephyr` 1.0.0. Frozen until Day 7 is done.
- [x] Board backed up before the first deploy (`../TCC_Artifacts/board_backup_20261010/`); the old motor demo `agv-motors-test` must not be started.
- [x] `deploy.sh`: deploy (stop, rsync, `app start`, version check, logs) and `pull <day>` (moves `/app/logs/` into `data/<day>/`, only between runs); `run <command>` came with Day 1 Firmware.
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
- [x] Motion limits in firmware: every moving mode takes a time limit, plus a distance limit (the farther wheel) where it drives; out-of-range requests are refused in the handler, and the STM32 ends the mode by itself, coasting in open loop and with a ramped stop in closed loop.
- [x] Wheels off the floor for the first run of all new motor code (`pwm_set`, directions and count signs, `step`, the 2 ms sampling, `ramp`); the rule still applies to every new mode.
- [x] Mode `step` (2): duty per wheel ≤ 30 %, ≤ 1000 ms, ≤ 500 mm, coast at the end; counts sampled every 2 ms by a `k_timer` and sent as `step_samples` (15 samples, ~193 B, every 40 ms), with loss detection in Python and one CSV per step (501/501 samples off the floor, 2 ms ± 20 µs).
- [x] Mode `ramp` (3) for `pwm0`: both wheels, duty rising at 10–200 thousandths/s up to ≤ 30 % (≤ 6 s), ≤ 200 mm, one sample per tick; off-floor data shows single counts well before sustained motion, so the analysis needs a sustained-motion criterion.
- [x] Floor identification session, robot fully assembled on the arena floor, LiPo freshly charged (12.6 V): steps at ±20, ±25, ±30 % and one ramp each way, all samples complete (`data/day1/20261011-195756_app_*`).
- [x] `./deploy.sh run <command>` sends the mode commands through `cmd/`; commands left there while the app was stopped are discarded at the next start (`cmd_discarded`).

**Analysis** (details in `docs/logs/day1-analysis.md`; scripts in `analysis/`, plots in `data/day1/plots/`)
- [x] First-order model per wheel and direction, fitted on counts (`day1_identify.py`, rms 1.3–5.1 counts, τ 96–164 ms per step); `pwm0` = start of sustained motion on the ramp (5 consecutive 20 ms intervals with a count): left 7.4 % fwd / 8.8 % bwd, right 6.9 / 7.2 %; K refit through the steps with that offset: left 7160 / 6668, right 7271 / 7509 counts/s per unit duty.
- [x] Slip check: K agrees across 20, 25 and 30 %; τ falls gradually with amplitude (e.g. right fwd 128 / 103 / 96 ms), so Rolds kept every step and τ is the mean per wheel and direction (left 154 / 147, right 109 / 143 ms).
- [x] PI gains (`day1_pi.py`, `pi_gains.csv`), decided by Rolds: pole-zero cancellation with Tcl = 0.1 s, feedforward `pwm0·sign(v) + (v + τ·a_ref)/K`, conditional integration, duty limited to 50 %. Simulated: ramp error ≤ 6 mm/s after the first 0.1 s, step 0 → 0.1 m/s with 18–21 % overshoot and 0.5–0.7 s settling, duty ≤ 0.32.
- [x] `wheel_pi` (pure C++, native tests through `uv run pytest`) and mode `speed` (4): one reference for both wheels, ramp or step; time, distance or command → ramped stop at 0.5 m/s², then coast.
- [x] Closed-loop tests on the floor, forward and backward (`day1_closed_loop.py`): ramp to 0.25 m/s at 0.5 m/s² with tracking error rms 5–6 mm/s (mostly count quantization), 100 ms-smoothed max 6.7–12.8 mm/s while ramping up and 6.0–7.4 mm/s at 0.25 m/s; step 0 → 0.1 m/s with 10–17 % overshoot, settling 280–420 ms to ±10 %; duty ≤ 0.42, never saturated; close to the simulation. Bridge stack peak 896 B (≥ 1152 B untouched), 0 overruns.
- [x] `encoder_guard` (approved by Rolds): ends `speed` at once, coasting, with reason 5 = `encoder` when a wheel is driven at |duty| ≥ 20 % for 200 ms without a count; replayed on the recorded runs it trips only on the unpowered one, and on the board with one encoder unplugged after 201 ms. The closed-loop modes of Days 2 and 3 use it too.
- [x] Extra: a 1 m closed-loop run (`speed 250 500 4500 937`, caps raised to 4500 ms and 1000 mm): 997 mm by the encoders, both wheels within one count, smoothed error ≤ 5 mm/s at 0.25 m/s.

---

## Day 2 — Straight line, odometry and calibration

**Firmware** (details in `docs/logs/day2-firmware.md`)
- [x] Starting point: `main` cleaned of the Day 1 identification code (archived in branch `day1`, tag `day1-final`).
- [x] Odometry at 20 ms, midpoint integration (`d = (dL + dR)/2`, `dθ = (dR − dL)/b`, `x += d·cos(θ + dθ/2)`, `y += d·sin(θ + dθ/2)`, `θ += dθ`): pure module `odometry` (native tests), m/count per wheel, θ not wrapped, `double` (a `float` θ drifts ~4·10⁻⁴ rad in two turns); one count read per tick, shared with the recorded samples; pose in `status`. On the floor, 997.4 mm by odometry for 998.3 mm of counts.
- [x] Heading PI (D = 0, `kd` removed, decided by Rolds), Kp = 2.3 s⁻¹, Ti = 1.0 s from `day2_heading.py` (in the simulated 1.38 m, 103 mm of lateral drift without it, < 1 mm with it); pure module `heading_pi` and the wheel layer `drive` (`vL = v − ω·b/2`, `vR = v + ω·b/2`, each wheel converted with its own m/count). It holds the odometry heading, so it only corrects what the encoders see. On the floor: heading within ±5 mrad and lateral offset within ±0.3 mm by the encoders; each run ends 1–5 mrad off its start heading (steering holds in the last 1.5 cm).
- [x] `motion_profile` (pure, native tests): one tick of the Motion law on a remaining distance or angle, with the commanded acceleration for the feedforward. The sampled law brakes up to ~8 % harder than a in the last ~6 cm (~2.6 mm past an ideal stop), accepted.
- [x] `straight` (5), developed from `speed`: stops at the target along the start heading; ends by target (reason 6), time, a 10 cm overshoot guard, command or encoder guard; `run_end` (start and end poses, constants used) and `run_samples` (8 values per tick, 1600-sample buffer) for the Python cross-check. On the floor, 5 × 1380 mm forward and backward, all by target.
- [x] In-place rotation on the angular profile (α = 2a/b, ω ramps down below 3°, ends with ω = 0), for `umbmark` and Day 3's ROTATE: 90° turns end 0.5–0.75° short off the floor and 0.45–0.48° short on average on the floor (U1 and U2, −24 to +6 mrad); the next leg's heading PI takes it up.
- [x] `umbmark` (6): four legs and four 90° turns to corners and headings fixed by the start pose, the fourth turn back to the start heading (as in the paper); 23.5 s per 1 m square at 250 mm/s; ramped stops by command and time mid-turn. `spin` dropped (UMBmark gives b), `speed` (4) retired; codes 1–4 stay unused.
- [x] Encoder guard kept: Rolds proposed removing it, but with the robot pushed against a wall the slipping wheels ended by time and the locked ones by the guard in ~240 ms, and it is the only stop for a dead encoder.
- [x] A and B re-measured by Rolds for a rear reference point (40.75 mm behind the axle): A_ref = (0.137, 0.745), B_ref = (1.540, 0.745), 1403 mm apart; the earlier A and B came from a wrong measurement.

**Linux / PC** (details in `docs/logs/day2-linux.md`)
- [x] Python reference of the odometry (`analysis/odometry.py`, `tests/test_odometry.py`) and `day2_odometry_check.py`, fed with the recorded samples: every run of Day 2, off the floor and on it, `straight` and `umbmark` (θ past 2π included), agrees with the firmware within 1 µm and 1 µrad; per-phase table and path plot for `umbmark`.

**Bench** (details in `docs/logs/day2-bench.md`; scripts in `analysis/`, data and plots in `data/day2/`)
- [x] Order of UMBmark (Borenstein and Feng, IEEE Trans. Robotics and Automation 12(6), 869–880, 1996): the scale Es first with a tape, then the wheel ratio Ed and the track error Eb.
- [x] Real pose (decided by Rolds on the bench day): from a tape cross on the floor, the rear reference point along and across the line and a front point on the centreline across it, sin θ = (dyf − dy)/L; error = real − odometry (the paper's Eq. 3.1, decided by Rolds), in each run's start frame (`analysis/bench.py`, tested).
- [x] S1, nominal constants, 5 × `straight 250 500 8000 1403` from A: εx −26.7 ± 2.2 mm, εy +16.1 ± 3.0 mm (left), εθ −4.1 ± 1.5 mrad → Es = 0.98103, 0.157632 mm per count.
- [x] U1, Es corrected, 5 CCW + 5 CW 1 m squares on tape lines c1–c4 (starts Q1 = (0.459, 0.25) and Q4 = (0.459, 1.25)): centroids CW (−0.9, −4.6) mm, CCW (30.2, −29.0) mm, E_max,syst = 41.9 mm; the x and y estimates agree (α −0.42 / −0.35°, β 0.45 / 0.48°) → Ed = 1.00176, Eb = 0.99575.
- [x] Calibrated constants in `config.h` (`kScaleEs`, `kCorrLeft`, `kCorrRight`, `kTrackEb`): 0.157493 mm (left) and 0.157771 mm (right) per count, b = 216.08 mm; README *Calibration* filled.
- [x] After: U2 E_max,syst = 8.1 mm (CW 3.0 mm, CCW 8.1 mm), below 3·SEM (11.3 mm), so no second correction; S2 εx 0.5 ± 0.4 mm, εy +4.3 ± 4.7 mm, εθ −7.3 ± 0.7 mrad (real heading 0; the odometry logs ~7 mrad from the last 1.5 cm). The run-to-run spread is unchanged (6–11 mm rms in UMBmark).
- [x] Every bench session: 0 overruns, 0 encoder errors, no `hook`, Bridge stack peak ≤ 904 B.

---

## Day 3 — Point-to-point control, Bridge and UI: A→B without obstacles

**Firmware** (details in `docs/logs/day3-firmware.md`)
- [x] Starting point: `main` cleaned of the Day 2 calibration analysis (archived in branch `day2`, tag `day2-final`); `analysis/bench.py` kept `pose_from_tapes` and `run_error`, then was removed during Day 3.
- [x] Decided by Rolds before the code: the waypoint follower runs on the STM32 (it needs the pose of the same tick) and the mission on Linux; `straight` (5) and `umbmark` (6) transformed into the follower in place, codes 5–6 stay unused; `set_path` starts the motion; no time or distance limit and no 5 cm timeout fallback (he watches every run, and a runaway is a failed run, registered).
- [x] `follower` (pure C++, from Day 2's `tick_turn` and `tick_leg`): IDLE → ROTATE → DRIVE → ARRIVED over ≤ 32 absolute waypoints. ROTATE to θ + wrap(bearing − θ), the shortest turn added to the unwrapped θ, on the Day 2 angular profile; DRIVE with `u` and the heading target re-aimed every tick and frozen within 10 cm, the ramp on the along-track `s = (w − p)·u`, back to ROTATE above 30°; a stop at every waypoint, and a waypoint within 1.5 cm counts as reached. Native tests on a robot that answers a tick late: A→B ARRIVED in 6.24 s, 4.2 mm past the waypoint; 3 cm off and 3° skewed converges to 2.0 mm lateral; a 45° push brakes, rotates again and arrives within 4.0 mm.
- [x] Mode `path` (7) and the Bridge, every handler through the command queue: `set_path` (1–32 waypoints in integer mm, refused unless the wheels are still, without an `hb` in the last second or outside the arena), `reset_pose(x_mm, y_mm, θ_mrad)` (only with no run open), `stop` (ramped pause), `mode idle` (ramped end), and `pose` every 2nd tick (25 Hz: `t_ms, x, y, θ, state, path_id, wp_idx`; ARRIVED holds until the next path).
- [x] A run is the whole mission (decided by Rolds): from the first `set_path` to the goal or a failure, replans included; `stop` pauses it and the next `set_path` is a replan with no wait, `idle` ends it. Every tick is recorded, pauses included, into a 60 s buffer (3000 samples, 96 KB; 104 416 B of RAM left), and `run_end` (p2 = paths in the run) and the samples go out only when it ends.
- [x] Heartbeat watchdog: 1 s without `hb` during a run, paused included, ends it (reason 7) and leaves the wheels in short brake, its only use besides emergencies.
- [x] Off the floor: three paths ended by target with the right signs (a +90° turn and a 180° turn the shortest way), 0.4–0.8 mm short of the waypoint; `stop` mid-leg paused the run; `reset_pose` in the pause and `set_path` while turning were refused; a replan in the same run ended by target with p2 = 2 in one samples file (1059 samples, the 15.2 s pause recorded); `idle` mid-turn ended by command on the ramp; `docker pause` ended by heartbeat ~1 s after the last `hb`.
- [x] On the floor, sent with `./deploy.sh run` (they count, decided by Rolds): **5 of 5 A→B and 3 of 3 on a 5-waypoint path** (A → (600, 745) → (900, 1000) → (1250, 1000) → (1250, 745) → (1581, 745), turns of ±40° and ±90°), with P inside the 5 cm circle around B_ref in all 8 (the arrival error is measured with the tape cross on Day 7, S0). By odometry, A→B ended 0.1–0.6 mm short of the waypoint in 6.16–6.20 s, the 5-waypoint path stopped within 1.3 mm of every waypoint in ~14.2 s, and the heading at the end was 3–11 mrad off (steering holds in the last 1.5 cm). The simulation predicted ~4 mm past; on the floor it stops short.
- [x] Every session: firmware and Python odometry (`analysis/odometry_check.py`, which was `day2_odometry_check.py`) agree within 0.8 µm and 0.8 µrad on all 14 runs, the pause, the replan and the command and heartbeat ends included; 0 overruns, 0 encoder errors, Bridge stack peak ≤ 992 B (≥ 1056 B untouched); two `hook`s of ~4 ms, each when a 5-waypoint `set_path` arrived with the robot stopped.

**Linux** (details in `docs/logs/day3-linux.md`)
- [x] Decided by Rolds: Start runs only A→B until the planner arrives (Days 4–6); Stop sends `idle` (the run ends and its metrics go out), and `stop` stays internal for the Day 6 replan; the clock sync is recorded as columns of the `pose` log.
- [x] Mission manager (`python/mission.py`, pure, tested with a fake Bridge): the mission thread is the only sender of motion commands and also takes Start/Stop from the UI and `start`/`abort` from `cmd/`. Start sends `reset_pose(178, 745, 0)`, then `set_path(id, [1581, 745])` only if that was acked, and waits for ARRIVED on the last `wp_idx` of its `path_id` (or its `run_end` by target); any other `run_end` fails it. The Bridge handlers only store data and never call the Bridge.
- [x] Center ↔ axle (`python/arena.py`): the start axle is A − 7 cm = (0.178, 0.745), and `pull_back_goal()` pulls the last waypoint 7 cm back along the last segment, so the A→B path is the axle at (1.581, 0.745) with the center on B. The UI draws the body around the center from `axle_to_center()`, so the 7 cm lives only in `arena.py`.
- [x] Clock sync (`python/clock_sync.py`): the STM32 and Linux clocks drift 895–901 ppm apart (not the tens of ppm assumed), so a 30 s sliding minimum lagged the offset by −27 ms; the window is 2 s (decided by Rolds): −1.7 ms bias, median `delay_ms` 2 ms, p99 7 ms. Every `pose` row logs `offset_s`, `delay_ms` and `t_linux`, and the `Pose` handed to the mission carries `t_linux`.
- [x] Flask UI (`python/webui.py`): Start / Stop, the arena, the path and the live pose on a canvas, `GET /state` polled at 5 Hz. The `flask_video_webui` brick now creates its Flask app in `__init__`, with `video()` waiting for Day 5.
- [x] Per-run logs: `*_app_pose.csv`, `*_app_paths.csv` (every `set_path` and its ack) and `*_app_events.csv` (`mission_*` events); 56 tests pass.
- [x] On the board: Start from the page drove A→B by target in 6.14 s (P in the circle); Stop aborted two missions with a ramped stop, the run ending 0.53–0.59 s after the click; 0 overruns, no `hook`. README *Running a mission*, *Logs*, the Bridge table and *Status* filled.

---

## Day 4 — Dataset day + offline planner

**Bench (most of the day)**
- [x] Capture tool in the app (`python/capture.py` + the Capture button on the mission page): the dataset frames come from the code path inference uses on Day 5, downloaded as lossless `im_N.png` (1280 × 720) to the PC, nothing written on the board; removed from the page after the dataset (saved in a tag and branch just like the other saved tags, but not as day4final -> instead, we will go with day4 dataset collection).
- [x] Capture the dataset on the MDF arena with the mounted camera: all obstacle classes, 0.15–1.0 m, varied angles and positions, several lighting conditions, background-only frames. (Captured only the box and background classes in this first moment, the other classes will be taken after one class only works)
- [x] Before training, choose the impulse's resize mode and record it with the resulting horizontal FOV in the README: "Squash".
- [x] Label and train in Edge Impulse (YOLO-Pro); export the Linux `.eim` (aarch64), put it in `models/` on the PC and `chmod +x` it.
- [x] Smoke test of the new `.eim` inside the app container (moved here from Day 1): it loads and runs, but returns no boxes, also with Edge Impulse's own runner, while the network inside it, run with LiteRT, finds them; the detector runs the float32 `.tflite` with LiteRT instead (decided by Rolds on Day 4, `docs/logs/day4-bench.md`).
  - record the inference FPS, including the conversion, the resize and the decoding. This de-risks Day 5.
- [x] Measure each obstacle class: width, depth and height. With Squash, check the narrowest class at d_max in model-input pixels (≈ W·907/Z · S/1280 for a width W at depth Z and an S-wide input). Box (the only class so far): 80.2 × 80.2 × 75.2 mm (h), ~13 × 22 model px at 0.7 m, circumscribed radius 56.7 mm.

**PC (in parallel while training runs)**
- [ ] Occupancy grid 5 cm (40 × 30 cells), in axle coordinates.
- [ ] Inflation: walls by 24.6 cm (21.6 cm rotation radius + 3 cm margin), except the wall behind A (x = 0), which is not inflated (decided by Rolds in the Day 3 review, so the start cell is free); obstacles by 24.6 cm + the circumscribed radius of the class footprint (center to farthest corner). Free axle corridor: x ≤ 1.754, y ∈ [0.246, 1.254]. Paths never cross inflated cells (no escape rule): no path fails the run.
- [ ] Dijkstra, 8 neighbours (diagonal cost √2), no corner cutting.
- [ ] Line-of-sight path simplification on the inflated grid.
- [ ] Detection association: same class within ~20 cm = same obstacle (average its position). The radius is a parameter, revisited on Day 5.
- [ ] "Path blocked?" check, with hysteresis:
  - plan with the full inflation (24.6 cm + footprint radius);
  - the remaining path is blocked only if it enters the inflation without the 3 cm margin (21.6 cm + footprint radius);
  - run the check for new obstacles and for position updates;
  - check that a 1–2 cm shift of a known obstacle does not trigger a replan.

**README:** start *Obstacle detection*: classes, obstacle dimensions, dataset size, model.

**Done when:** the model runs on the board and the planner checks above hold on the PC.
**Record:** dataset size per class, model metrics, obstacle dimensions, inference FPS from the smoke test.

---

## Day 5 — Detector on the robot + distance calibration

**Linux**
- [ ] Capture and inference as two threads:
  - capture thread (`python/capture.py`, built on Day 4 for the dataset): reads every frame and keeps only the latest (frame, timestamp) pair; a failure in `cam.open()` or `cam.read()` is logged as `camera_error`. Still to do: check the V4L2 timestamp on the board;
  - inference thread, on the latest pair: BGR → RGB, Squash to the model input, 0..1, LiteRT, decoding with threshold and NMS; map each bbox back to 1280 × 720 (done on Day 4);
  - draw bboxes on the BGR frame in the Flask stream, encoded at ~640 × 360 and ≤ 10 fps so it does not compete with inference for CPU.
- [ ] Method (b): floor homography from 8–12 tape marks measured in the robot frame (axle origin). It also gives the **bearing**, measured from the camera, used by both methods.
- [ ] Method (a): `Z = k/h` with one k per class, the depth along the optical axis, combined with the bearing, Camera. Fit k against the camera → front-face depth (axle → front face − 0.17 m).
- [ ] Obstacle position = front face F + depth/2 along the bearing, i.e. the footprint center.
- [ ] Filters: drop detections beyond d_max (start at 0.7 m of depth Z), bboxes touching the image bottom (full-frame coordinates) and positions outside the arena; require 3 consecutive frames.

**Bench**
- [ ] Each class at 0.3–1.0 m every 10 cm, centered and to each side, 20 detections per position (mean and standard deviation) → error versus distance for (a) and (b). Tape from the axle to the obstacle's front face, plus the lateral offset.
- [ ] 5 approaches per class while the robot drives and brakes toward the obstacle: with the lens 5.45 cm above the floor, (b) shifts ~1.6 cm per 0.1° of pitch at 0.7 m (Z²/h), which the static bench does not show.
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
  - replans from that pose (Dijkstra + simplification), sends the new `set_path` with a new `path_id`, and resumes.
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
- [ ] Tape-measure the reference and front points from the cross at B → real pose (x, y, θ) → real center.
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
