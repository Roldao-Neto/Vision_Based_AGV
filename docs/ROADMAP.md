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
- [x] **Board versions first**, before anything else is set up or recorded: read `arduino-app-cli version`, `arduino-router version` and the `arduino:zephyr` platform version, and compare them with the versions the Bridge analysis in `CLAUDE.md` was verified against (arduino-app-cli ≥ 0.11, arduino-router ≥ 0.8.0, core 1.0.0). If any is older, run `arduino-app-cli system update` now: it is the last update until Day 7 is done (see `CLAUDE.md`, Freezing the board's versions), and an update after the versions are recorded or the tick is measured would mean doing them again.
- [x] Before the first `deploy.sh`:
  - look at the target app folder on the board and copy to the PC anything that exists only there, since the sync's `--delete` removes it;
  - until the first deploy replaces it, the app on the board may still be the archived one (`../TCC_Artifacts/applab_raw_code/`), whose sketch is the old motor demo: an endless forward/backward loop with no limits, which the hardwired STBY no longer stops. Do not start it with the LiPo connected and the wheels on the floor.
- [x] `deploy.sh` (see `CLAUDE.md`, Development workflow):
  - stop the app, rsync `app.yaml`, `python/`, `sketch/`, `bricks/`, `models/` to the board over Wi-Fi, then `arduino-app-cli app start` and follow the logs;
  - once `docs/board-versions.txt` exists (see below), compare the "Used library …" lines printed by `app start` with it and stop the app if any differ;
  - `logs/` (`/app/logs` in the container) and `.cache/` on the board are never touched by `--delete`;
  - `deploy.sh pull <day>` (e.g. `day1`), only between runs:
    - stops the app first and leaves it stopped, so no file is copied while still being written (`app stop` also resets the STM32, see `CLAUDE.md`, Development workflow);
    - copies the files in `/app/logs/` into `data/<day>/` on the PC with `--ignore-existing`, so nothing already there is overwritten, and only then deletes them on the board (`rsync --remove-source-files` deletes each file only after it has been transferred), so each pull brings only new files and the board's storage does not fill up;
    - lists any file left in `logs/` (a skipped name collision).
- [x] Per-run logs (see `CLAUDE.md`, Development workflow): every file name is unique (date and time plus mode and parameters), and every row is flushed when written.
- [x] Confirm the board keeps OpenCV 4.13 after installing `python/requirements.txt`. The container image ships and pins OpenCV 4.13.0+1ddb20b, so `requirements.txt` must not list it (see `CLAUDE.md`, Local Python environment).
- [x] `sketch/sketch.yaml`:
  - add a scratch app in App Lab that uses `Arduino_RouterBridge` and copy what it generates; on current platforms that is no `libraries:` entry, since the libraries come with the platform (see `CLAUDE.md`, Current code state);
  - set `fqbn: arduino:zephyr:unoq`.
- [x] Patched Bridge copy (see `CLAUDE.md`, Bridge limits and threading):
  - copy `src/` and `library.properties` from the `Arduino_RouterBridge` 0.4.3 release tag into `sketch/libraries/Arduino_RouterBridge/`, and add `libraries: - dir: libraries/Arduino_RouterBridge` to `sketch.yaml`;
  - apply the two `// AGV patch` changes to `src/bridge.h`: overridable `UPDATE_THREAD_STACK_SIZE` set to 2048, and the stack filled with `0xAA` before `k_thread_create`. Check that `diff` against the release shows nothing else.
- [x] Record the board's software versions, after the scratch app (adding a library in App Lab refreshes the library index) and with the patched copy in place: `arduino-app-cli version`, `arduino-router version`, the `arduino:zephyr` platform, and `arduino_app_bricks` (`importlib.metadata.version` from the app). Save the "Used library …" lines printed by `app start` in `docs/board-versions.txt`. Pin that `arduino_app_bricks` release tag in `pyproject.toml` and run `uv lock`. No `arduino-app-cli system update`, `apt upgrade` or App Lab board update until Day 7 is done (see `CLAUDE.md`, Freezing the board's versions).
- [x] **Check before any Bridge work:** the `Arduino_RouterBridge` line printed by `app start` must point to `sketch/libraries/Arduino_RouterBridge`. If it points to the platform's copy, the bridge thread still has the 500-byte stack that overflows silently: stop and ask how to proceed.
- [x] Minimal app: sketch and Python exchange a Bridge ping; Python sends the `hb` heartbeat (5 Hz).
  - MCU handlers follow the command queue rule and take integer arguments only (see `CLAUDE.md`, Bridge limits and threading). Store `k_current_get()` inside a handler and in `loop()`, report both from `loop()` through `notify` (handlers make no Bridge calls), and record which thread runs the handlers.
  - Bridge stack peak (see `CLAUDE.md`, Bridge limits and threading): find the bridge thread from a handler, scan its stack from `loop()`, send the peak in telemetry, and wire the emergency for fewer than 512 untouched bytes. Check the scan once by reading it right after boot: the peak must be well below 2048 bytes and above 0.
  - Python retries `ping` until the MCU answers before sending anything else.
  - Test the size limit: a 32-waypoint `set_path` in integer mm (217 bytes) must be acked; the same path in floats (601 bytes) must be rejected. Record both. Run the float test last: if the router let it through, it would block the MCU's RPC until the app restarts.
- [x] Editor support for the sketch:
  - install `arduino-cli` and the `arduino:zephyr` core on the PC, at the platform version recorded from the board (`arduino-cli core install arduino:zephyr@<version>`), so the editor sees the same headers the board compiles with;
  - confirm the FQBN with `arduino-cli board listall`;
  - generate `compile_commands.json` with `arduino-cli compile --only-compilation-database --build-path build sketch`, run from the repo root. The build output goes to `build/` at the root (gitignored), never inside `sketch/`, because `deploy.sh` syncs `sketch/` to the board. clangd finds `build/compile_commands.json` by itself (it searches each parent directory and its `build/` subdirectory);
  - point Zed's clangd at it, with `--query-driver` for `arm-zephyr-eabi-g++` in the project `.zed/settings.json`, so `Arduino.h` and the Zephyr APIs resolve.
  The current `.clangd` only makes clangd parse `.ino` as C++.
- [x] Control tick in `loop()`, scheduled with `micros()` (`next += 20000`). It applies the commands queued by the Bridge handlers at its start; apart from the `hb` timestamp, nothing else is shared with them.
  - If the loop falls more than one period behind, resync `next` to now and log the overrun instead of running catch-up ticks with a near-zero dt.
  - Telemetry goes out with `Bridge.notify`, never with `Serial` (see `CLAUDE.md`, Bridge limits and threading).
  - Log its jitter: expect ~1–2 ms (the Bridge sleeps 1 ms after every `loop()`, and its thread preempts `loop()`).
  - Only if the jitter is unacceptable, move the tick to its own `k_thread`.

**Firmware**
- [ ] Split `sketch/sketch.ino` into modules before it grows, with no change in behaviour:
  - modules go in `sketch/src/<module>/` (`.h` + `.cpp`), included from the sketch as `#include "src/<module>/<module>.h"`. arduino-cli compiles `src/` recursively; checked on the PC with arduino-cli 1.5.1 and `arduino:zephyr` 1.0.0 (a test module in a copy of the sketch compiled, linked and got its own entry in `compile_commands.json`). The board builds with arduino-cli 1.4.2, so check the first `app start` after the split. `deploy.sh` already syncs all of `sketch/`;
  - not local libraries with `dir:` in `sketch.yaml` (each needs a `library.properties` and its own entry, and only pays off for code shared between sketches);
  - every `.cpp` includes `<Arduino.h>` explicitly (only the `.ino` gets it for free). `Bridge` comes with it: `Arduino.h` includes the variant's `postvariant.h`, which includes `Arduino_RouterBridge.h` (`arduino:zephyr` 1.0.0, `variants/arduino_uno_q_stm32u585xx/postvariant.h`);
  - one namespace per module, its state `static` inside the `.cpp`;
  - proposed split: `config.h` (pins, tick period, arena limits), `commands` (`k_msgq`, staged path under the mutex, drain), `handlers` (Bridge handlers and the bridge thread id), `tick_timing` (lateness, tick body, hook time), `bridge_stack` (stack scan and emergency); later `motor_driver`, `encoders`, `wheel_pi`, `odometry`, `heading_pid`, `p2p_controller`. `sketch.ino` keeps only `setup()`, `loop()` and `tick()`;
  - optional: pure-math modules (speed and rotation ramps, `s = (w − p)·u`, PI, odometry) written without `Arduino.h`, so they also compile with the PC's `g++` for native unit tests;
  - after the split, deploy once and check that `status` and `hook` match a run of the unsplit sketch, then update *Current code state* in `CLAUDE.md`.
  - Still to decide: when (before the TB6612 driver or later), the final module list, whether native C++ tests start now, and which log records it.
- [ ] Own TB6612 driver: signed PWM per wheel, explicit brake and coast. Left = D6/D7/D8, right = D9/D10/D11, STBY is hardwired to 3.3 V.
  - In `setup()`, call `analogWrite(D6, 0)` and `analogWrite(D9, 0)` once: that initializes the deferred PWM timers and switches the pins to them. From then on set ~20 kHz with Zephyr `pwm_set` only (period 50 µs, see `CLAUDE.md`, Architecture) and check its return value; a later `analogWrite` would re-apply 500 Hz.
  - If `pwm_set` is not reachable from the sketch, keep 500 Hz and do all identification at that frequency.
- [ ] x4 quadrature interrupts (`CHANGE`, pins as `INPUT_PULLUP`): left D2 (A) / D4 (B), right D3 (A) / D5 (B). Forward motion must count positive on both wheels.
- [ ] Mode `count`: mark the wheel, turn it 10 times by hand, read counts → **counts per wheel revolution**.
- [ ] Fixed 20 ms control tick; wheel speed from count deltas divided by the **measured** dt.
- [ ] Motion limits in firmware (see `CLAUDE.md`, Bridge contract, `mode`): every mode that moves the robot (`step`, the `pwm0` ramp, the closed-loop tests, and the Day 2 modes) takes a time limit, plus a distance limit where it drives, and the STM32 ends it by itself when either is reached, ramped in closed loop and coasting in open loop. The heartbeat watchdog only arrives on Day 3 and never covers calibration modes, so a lost ssh, Wi-Fi or Python must not leave the robot driving into the wall.
- [ ] Wheels off the floor for every first run of new motor code (direction and counting signs, `pwm_set`, each new mode with its limits) before running it on the arena floor: a Zephyr fatal error keeps the PWM at its last duty (see `CLAUDE.md`, Pin map).
- [ ] Identification conditions, for every `step` run and the closed-loop tests:
  - the robot fully assembled (camera, power bank, LiPo) on the arena floor, since mass and floor set K, τ and `pwm0` (see `CLAUDE.md`, Architecture);
  - the LiPo freshly charged at the start of each identification session (K scales roughly with the supply voltage, ~12 % between 12.6 V and 11.1 V, which the PI integrator absorbs); if the charger shows the voltage, save it with the CSVs.
- [ ] Mode `step`:
  - apply small PWM steps to both wheels together (20 %, 25 %, 30 %, never above 30 %), forward and backward, each ≤ 1 s, ending by coasting (PWM 0), never braking. At these duties the motor's starting torque (about duty × stall torque) should stay below what makes the wheels slip; the consistency check in Analysis catches it if not. During each step, store the cumulative counts with their `micros()` time every 2–5 ms in RAM, then send them to Python → CSV in notifications of ~200 bytes. Each notification carries the step's id and the index of its first sample, and the last one also the sample count, so Python detects a lost notification and the step is repeated instead of fitted. Fitting the model to counts (position) avoids differentiating noisy speeds, and a time constant of a few tens of ms would get only a couple of samples at 20 ms;
  - add a slow PWM ramp per wheel and direction to find the start-up PWM `pwm0` (static friction).

**Analysis**
- [ ] Fit a first-order model (gain K, time constant τ) and the static-friction offset `pwm0` per wheel and direction from the step and ramp CSVs, with K in counts/s per unit of PWM (the speed loop runs in counts/s, see `CLAUDE.md`, Architecture). The analysis scripts live in `analysis/` (PC only), read `data/day1/` and write their plots to `data/day1/plots/`.
- [ ] Slip consistency check: K and τ fitted at 20 %, 25 % and 30 % must agree. A step whose τ is clearly smaller than the others slipped (the wheel spun up faster than the robot could): drop it and keep the amplitudes below it.
- [ ] Compute PI gains from the model; feedforward `pwm = pwm0·sign(v) + v/K` with the low-speed rule in `CLAUDE.md`, Architecture; anti-windup.
- [ ] Closed-loop tests, both wheels together, in the same conditions as the `step` runs, logging the commanded PWM:
  - a 0.5 m/s² ramp from 0 to 0.25 m/s, the real operating profile: record the speed tracking error;
  - a small speed step 0 → 0.1 m/s: record overshoot and settling time. The PWM must not saturate during the step, since a saturated PWM is what slips the wheels (see Day 2); if it does, use a smaller step.

**README:** fill *Setup and running* (PC `uv sync`, `deploy.sh`, starting the app, editor setup).

**Done when:** both wheels follow the 0.5 m/s² ramp to 0.25 m/s with a recorded tracking error and the 0 → 0.1 m/s step with known overshoot and settling time, the 32-waypoint `set_path` is acked, and the bridge stack peak is measured with the encoders running and more than 512 bytes untouched.
**Record:** counts/rev, PWM frequency, K, τ and `pwm0` per wheel, K and τ per step amplitude (slip check), LiPo voltage if the charger shows it, PI gains, ramp tracking and step response plots, loop jitter, Bridge size test, the thread that runs the Bridge handlers, bridge stack peak (after the `set_path` tests and the closed-loop steps, i.e. with traffic and encoder interrupts), software versions.

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
