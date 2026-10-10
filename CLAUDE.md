# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Undergraduate thesis (TCC, Unifei): a differential-drive AGV on an **Arduino UNO Q** that drives from a fixed start A to a fixed goal B, avoiding obstacles it discovers with a camera.

- **Localization is wheel odometry only.** ArUco markers, solvePnP, camera intrinsics and vision/odometry fusion were dropped. Do not reintroduce them.
- Vision is used only to detect obstacles and estimate where they are.
- The day-by-day plan is in `docs/ROADMAP.md`.

## Working rules

- Code identifiers **and comments** are in English.
- Any doubt, ambiguity or conflict with the agreed design below must be asked, never assumed.
- **Work log for every ROADMAP sub-step.** When work starts on a block of a day in `docs/ROADMAP.md` (e.g. Day 1 Setup, Day 1 Firmware, Day 1 Analysis), create `docs/logs/day<N>-<block>.md` (e.g. `day1-setup.md`, `day1-firmware.md`) and update it **while the work happens**, after each step, never only at the end. Model: `docs/logs/day1-setup.md`.
  - Written in Portuguese, as a presentation of the work: explain the decisions (and who made them) and answer the questions a reader would have. Commands, code and identifiers stay as they are.
  - Follows the order of the ROADMAP items that were executed (with a short table of the real chronological order when it differs), and records everything, including errors, dead ends, extras and decisions.
  - For each item, always these five parts:
    1. what was done (and why);
    2. the commands and code used;
    3. a step-by-step explanation of what each command and piece of code does;
    4. the results, with explanations (numbers, tables, the data files in `data/<day>/`);
    5. conclusions.
  - Every fact keeps its source (library file and version, board file, measurement), and the final versions of the files written in that block go in an appendix.

## Architecture

The UNO Q has two processors linked by the **Bridge** (RPC through the `arduino-router` service on Linux):

- **STM32U585 (`sketch/`, Arduino sketch on the Zephyr core) — real time, 20 ms tick** run from `loop()`, scheduled with `micros()` (`next += 20000`), with speeds computed from the measured dt:
  - x4 quadrature encoder interrupts;
  - own TB6612 driver; PWM set with Zephyr `pwm_set` at ~20 kHz if the sketch can reach it (the devicetree default is 500 Hz, and `analogWrite` always re-applies that period). The PWM timers are `zephyr,deferred-init`, and only `analogWrite` initializes a timer and switches its pin to it, so `setup()` calls `analogWrite(pin, 0)` once on D6 and D9 and every later write uses `pwm_set` (D6 = `pwm3` channel 4, D9 = `pwm4` channel 3; the timers count at 32 MHz, so 50 µs is 1600 counts);
  - PI speed loop per wheel (first-order model + feedforward with a static-friction offset, `pwm = pwm0·sign(v) + v/K`), in encoder counts per second: each wheel's m/s setpoint is converted with that wheel's mm/tick, so K (counts/s per unit of PWM), τ, `pwm0` and the PI gains stay valid when Day 2 calibrates mm/tick (until then the conversion uses the nominal Ø 67.5 mm and the counts per revolution from `count` mode). The offset applies only while |v_ref| is above a few mm/s; below that the wheel coasts and the integrator is reset, so a stopped wheel stays quiet. K, τ and `pwm0` are identified with the robot fully assembled on the arena floor, so a change of mass or floor means identifying them again;
  - odometry;
  - heading PID;
  - point-to-point controller: rotate in place, then drive straight with the heading re-aimed at the waypoint.
  The STM32 owns the robot pose.
- **QRB2210 Debian (`python/`, `bricks/`, `app.yaml`):** camera, Edge Impulse detector, obstacle distance, occupancy grid, Dijkstra, path simplification, mission manager, Flask UI, CSV logs.

Bridge contract:

| Direction | Message | Content |
|---|---|---|
| STM32 → Linux | `notify("pose", t_ms, x, y, theta, state, path_id, wp_idx)` | 25 Hz (every 2nd tick). Axle pose in m and rad. `t_ms` is an integer (`millis()`); `path_id`/`wp_idx` identify the path and waypoint being executed |
| Linux → STM32 | `call("set_path", id, [x1_mm, y1_mm, ...])` | 1 to 32 **absolute** axle waypoints as **integer millimetres**; never relative commands; the start (current position) is not included. The ack means the path was queued: `pose` carries the new `path_id` once the tick applies it. Sent only while the robot is stopped (see Bridge limits: a large message holds `loop()` off ~35 ms) |
| Linux → STM32 | `call("reset_pose", x_mm, y_mm, theta_mrad)` | sets the odometry pose of the **axle** as integers (mm, mrad); at A it is (275, 745, 0), not A itself |
| Linux → STM32 | `call("stop")`, `call("mode", ...)` | `stop` is a ramped stop; `mode` switches mission and calibration modes (Day 1: `count`, `step`, the `pwm0` ramp and the closed-loop speed tests; Day 2: `straight`, `spin`, `umbmark`) with an integer mode code and integer parameters. Every mode that moves the robot also takes a time limit, and a distance limit where it drives, and the STM32 ends it by itself when either is reached (ramped stop in closed loop, coast in open loop) |
| Linux → STM32 | `notify("hb")` | 5 Hz heartbeat; STM32 brakes after 1 s without it (except in calibration modes, which rely on their own limits) |

Bridge limits and threading (verified in the library sources: `Arduino_RouterBridge` 0.4.3, `Arduino_RPClite` 0.3.1, `arduino-router`, `arduino-router-bridge` 0.5; the platform lists `Arduino_RPClite` 0.3.0 only as a minimum, the build takes the latest release, and 0.3.1 only changes how arguments are deserialized):
- A message to the MCU must fit in **256 bytes**: `Arduino_RouterBridge` uses `RPCRequest<DEFAULT_RPC_BUFFER_SIZE>` (= 1024/4 in `Arduino_RPClite`, not overridable) and announces that size to the router, which rejects larger calls (router ≥ 0.8.0). A larger message that did reach the MCU would never leave its decoder and would block every later RPC until a reset. Python packs floats as float64 (9 bytes), so 32 float waypoints would be 601 bytes; 32 waypoints in integer mm are at most 217 bytes. Python must send native `int`s (msgpack rejects `numpy.int64`).
- The link is LPUART1 at 115200 baud (~11.5 kB/s).
- **Handlers run on either thread.** `provide_safe` only tags a handler so that `loop()` may run it from `__loopHook`, but since `Arduino_RPClite` 0.3.0 the bridge thread takes tagged requests too. That thread has priority 5 and `loop()` has 14 (`CONFIG_MAIN_THREAD_PRIORITY`; the lower number runs first), so it tends to win: a handler can preempt the tick anywhere, and two handlers can interleave. Measured on the board on Day 1 (`data/day1/`): over 70 s, 256 handler calls ran on the bridge thread (named `bridge`) and 95 on the main thread.
- **Bridge thread stack: the sketch uses a patched copy of `Arduino_RouterBridge` 0.4.3.**
  - The problem: in 0.4.3, the latest release, the bridge thread has a 500-byte stack (`UPDATE_THREAD_STACK_SIZE`, a plain `#define` that cannot be overridden). The thread runs `update()` about every millisecond even with no traffic, and every pass keeps the 256-byte `RPCRequest` on that stack. `-fstack-usage` gives 8 + 368 + 48 + 72 = 496 bytes for `updateEntryPoint` → `BridgeClass::update()` → `RPCServer::get_rpc()` → `RpcDecoder::fetch_rpc_method()`, before their callees (msgpack decoding, `malloc`) and before the 32-byte exception frame that each encoder interrupt pushes onto the interrupted thread's stack (issue arduino-libraries/Arduino_RouterBridge#77, with crashes in the bridge thread reported on the UNO Q with core 1.0.0). The UNO Q build has no stack overflow detection (`CONFIG_HW_STACK_PROTECTION`, `CONFIG_STACK_SENTINEL`, `CONFIG_INIT_STACKS` and `CONFIG_ARM_MPU` are all off in the core 1.0.0 `.config`), so an overflow silently corrupts memory. 0.4.4 raises the stack to 2048 bytes, but it exists only on branch `ver_0_4_4_rc` (unreleased on 2026-10-10, with no date), so the project does not wait for it.
  - The copy: the 0.4.3 release (`src/`, `library.properties`, `LICENSE`; MPL-2.0, so the patched file stays MPL) lives in `sketch/libraries/Arduino_RouterBridge/` and is declared in `sketch.yaml` as `- dir: libraries/Arduino_RouterBridge`. The folder name must be exactly `Arduino_RouterBridge`: arduino-cli names a `dir:` library after its folder and then skips the platform's own `Arduino_RouterBridge` (`commands/instances.go`, "unless overridden in profile"), and `app start` only removes index entries from `sketch.yaml`, never `dir:` ones (arduino-app-cli `internal/orchestrator/sketch_libs.go`). Both checked in the arduino-cli sources used by arduino-app-cli ≥ 0.11 (arduino-cli 1.4.2), and confirmed on the board on Day 1: `app start` prints `Used library Arduino_RouterBridge (0.4.3) in /home/arduino/ArduinoApps/agv/sketch/libraries/Arduino_RouterBridge` and leaves `sketch.yaml` unchanged.
  - Only `src/bridge.h` differs from 0.4.3, and each change is marked `// AGV patch`:
    1. `#ifndef UPDATE_THREAD_STACK_SIZE` / `#define UPDATE_THREAD_STACK_SIZE 2048` / `#endif`, the same change as 0.4.4 (its only change to `bridge.h`);
    2. right after `k_thread_stack_alloc`, the stack is filled with the pattern `0xAA` before `k_thread_create`, so its peak use can be measured. The fill covers `UPDATE_THREAD_STACK_SIZE` bytes from the returned pointer, which is in bounds: the core's Zephyr (4.4.2-rc1, `CONFIG_DYNAMIC_THREAD_PREFER_POOL` with a pool of two 1024-byte stacks and `CONFIG_DYNAMIC_THREAD_ALLOC`) cannot serve 2048 bytes from the pool, so `k_thread_stack_alloc` takes `K_KERNEL_STACK_LEN(size)` bytes from the 32 KB system heap (Zephyr `kernel/dynamic.c`), and `stack_info.start` is that pointer.
  - Peak measurement: `setup()` stores the main thread's `k_current_get()`. A handler that runs on any other thread stores that thread's `k_current_get()` once: it is the bridge thread. `loop()` scans that stack upward from `stack_info.start` (`CONFIG_THREAD_STACK_INFO=y`) to the first byte that is not `0xAA`; the stack grows down, so everything above that byte is the peak use. The peak goes out in telemetry. If fewer than 512 bytes are still untouched, the STM32 treats it as an emergency: short brake, report, and refuse motion until restart.
  - The copy also pins `Arduino_RouterBridge` itself: a later 0.4.4 release changes nothing on the board, and moving to it means replacing the copy on purpose.
- **MCU handler arguments are integers only:** positions in mm, angles in mrad, modes as integer codes. A float argument would run FP instructions on the bridge thread, and with `CONFIG_FPU_SHARING=y` and lazy stacking every later exception frame on that thread's stack reserves 72 more bytes. Integers also keep messages small.
- **Command queue.** Every MCU handler validates its arguments, pushes one command into a single `k_msgq` (set up with `k_msgq_init` in `setup()`; the loader exports `k_msgq_*`) and returns. Waypoint lists are copied into static storage under a `k_mutex` before queuing, so handler stacks stay small. The tick drains the queue at its start, so commands apply between ticks and in arrival order (`reset_pose` before the `set_path` that follows it). The `hb` handler only stores a 32-bit timestamp. Handlers stay short and non-blocking, with no `Bridge` or `Serial` calls inside. Registering them with `provide_safe` is still fine.
- After every `loop()`, the Bridge's `__loopHook` sleeps 1 ms when no RPC is pending, and the bridge thread preempts `loop()` whenever it polls the link, so the tick has ~1–2 ms of jitter. Measured on Day 1 (`data/day1/20261010-171517_app_tick*.csv`, 7500 ticks, 146 s, 5 Hz `hb`, no overrun): tick starts are late by 0–1.1 ms, nearly uniform (99.89 % ≤ 1.1 ms, mean 0.6 ms), measured dt 18.7–21.6 ms, tick body ≤ 0.62 ms including the reports. One tick in the first 0.5 s window was 13.2 ms late (dt 7.8–33.0 ms in that window), while Python sent the three `set_path` calls of the size test: see the next point.
- **A large message to the MCU holds `loop()` off while it arrives, so `set_path` is sent only while the robot is stopped** (decided on Day 1). While a message is still arriving (217 B take ~19 ms at 115200 baud), every `decode()` re-parses the buffer prefix by prefix (`Arduino_RPClite` 0.3.1 `decoder.h`, `parse_packet`: `unpacker.feed(buffer, k)` for k = 1…N, O(N²) per call), every ~1 ms, on the bridge thread (priority 5, above `loop()`) and holding `read_mutex`, which `update_safe` in `__loopHook` waits for up to 10 ms. Measured on Day 1 (`data/day1/20261010-172717_app_*.csv`, 30 s phases at 2 Hz): each 32-waypoint `set_path` kept `loop()` from running for ~35–40 ms (usually ~10 + ~26 ms), the tick was up to 36 ms late, and 31 of 110 calls caused an overrun; the same happened with a variant registered with `provide` (bridge thread only), so it is not the handler. `ping` and `hb` (a few bytes) stayed below 1.8 ms (one 7 ms case), and idle below 1.7 ms. `stop`, `mode`, `reset_pose` and `hb` are small; only `set_path` is large. The mission thread therefore sends `set_path` only with the robot stopped (at the start, and after the ramped `stop` before a replan), where a lost tick does not matter; the tick stays in `loop()`. The sketch reports every pass outside `loop()` longer than 3 ms (`hook`), so a breach shows in the logs.
- `Serial` on the UNO Q is the Bridge `Monitor`: with no monitor attached, every write makes a blocking `mon/connected` RPC. Telemetry goes to Python with `Bridge.notify`, which keeps prints out of the control path.
- On Linux, provided handlers run one at a time on one dispatcher thread, so they only store the data (the `pose` handler appends the sample). A handler registered with `Bridge.provide` must not call `Bridge.call` (it raises `RuntimeError`).
- One thread sends every motion command (`stop`, `set_path`, `reset_pose`, `mode`): the mission thread from Day 3 on, with inference and the Flask UI posting events to it. `app start` flashes the sketch before it starts the Python container, but the MCU may still be in `setup()` (`Bridge.begin()` and the `provide` registrations) when Python starts, so Python retries a `ping` call until the MCU answers before sending anything else.

`t_ms` is used to match each camera frame with the pose at that moment. It is the **STM32 clock**, not synchronized with Linux, so it must never be compared directly with Linux timestamps:
- Python stores the Linux monotonic receive time of every `pose`.
- It estimates the clock offset as the minimum of `(receive − t_ms)` over a **sliding window** (~30 s), i.e. the least-delayed recent message. A minimum over the whole session would drift: the two clocks differ by tens of ppm, which adds up to ~0.1 s per hour.
- It converts poses to the Linux clock with that offset.
- Each frame is stamped with its V4L2 buffer time, `cap.get(cv2.CAP_PROP_POS_MSEC)`: for a UVC camera it is CLOCK_MONOTONIC (the clock of `time.monotonic()`), taken when the frame starts arriving. Check on the board that it reads a few tens of ms before `time.monotonic()` at the end of `read()`; if it does not, stamp right after `read()` instead.
- The capture thread reads every frame and keeps only the latest (frame, timestamp) pair, and inference runs in its own thread on that pair, so a frame is never older than its stamp. Inference inside the capture loop would leave frames waiting in the V4L2 queue, stamped late by a whole inference.
- Each frame is matched to the pose closest in time.

## Frames and constants

**Arena and goal**
- Arena: 2 × 1.5 m inside the MDF walls. Origin at the inner wall corner, x along the 2 m side, θ counter-clockwise, SI units.
- Robot center: A = (0.345, 0.745), B = (1.725, 0.745), θ0 = 0. At A the robot's rear is 23.5 cm from the wall.
- A and B sit exactly on the edge of the free corridor (see Planner): the start axle is in the first free cell and B is in the last free cell, so the robot never starts in an inflated cell.

**Reference point**
- The STM32 tracks the **axle midpoint**, which is 7 cm behind the robot center.
- The grid, the planner and every waypoint sent to the STM32 use **axle coordinates**. Centers appear only at the edges:
  - start axle = A − 7 cm in x, i.e. (0.275, 0.745);
  - the path is planned to B, then the last waypoint is pulled back 7 cm along the last segment, so the **center** ends at B.

**Robot geometry**
- Track b ≈ 21.7 cm, still to be refined by calibration.
- Wheel Ø 67.5 mm. Motors JGB37-520 12 V 333 rpm; encoder counts per revolution are not known yet and are measured in `count` mode.
- Body 22 × 24 cm, axle 4 cm from the rear, steel-ball caster at the front.
- The farthest point from the axle is 21.6 cm away. This is the rotation sweep radius used for obstacle inflation.

**Motion**
- 0.25 m/s cruise, 0.5 m/s², rotation up to 90 °/s with angular acceleration α = 2a/b ≈ 4.6 rad/s², so each wheel also accelerates at 0.5 m/s².
- ROTATE uses the same profile on the heading error e: `ω = min(ω_max, ω_prev + α·dt, sqrt(2·α·|e|))`, with the sign of e. Once |e| is below 3° (overshoot included), |ω| ramps down as `|ω| = max(0, |ω_prev| − α·dt)`, and the rotation ends when the commanded and measured ω are zero. Ending it at 3° while still turning (~40 °/s at that point of the profile) would be an angular version of the one-tick stop forbidden below.
- The robot stops at every waypoint. The deceleration ramp brings the speed to zero exactly at the waypoint (at 0.5 m/s² it is still at ~0.22 m/s 5 cm before it).
- The remaining distance is measured **along the track**: `s = (w − p)·u`, where `u` is the direction to the waypoint (re-aimed every tick, frozen in the last 10 cm). The ramp is `v = min(v_max, v_prev + a·dt, sqrt(2·a·max(s, 0)))`. The Euclidean distance must not be used: with a lateral error it never gets small, and after an overshoot it grows again and the ramp accelerates.
- Once `s` is below 1–2 cm (this includes `s < 0`, an overshoot), steering stops and the speed ramps down as `v = max(0, v_prev − a·dt)`: at 2 cm the ramp is still at ~0.14 m/s, and cutting it to zero in one tick would brake at ~7 m/s². ARRIVED is declared when the commanded and measured speeds are zero. 5 cm is only a safety limit: if the robot has not converged after a timeout, it accepts a stop within 5 cm and logs it.
- Do not confuse this with the success criterion of the experiments (real center within 5 cm of B), which is measured with a tape.
- `stop` and every planned stop decelerate at 0.5 m/s². The TB6612 short brake is only for the heartbeat watchdog and emergencies, because braking hard at 0.25 m/s slips the wheels and corrupts odometry.

**Planner**
- Occupancy grid of 5 cm cells (40 × 30).
- Walls inflated by 24.6 cm (rotation radius + 3 cm margin). Obstacles inflated by 24.6 cm plus the circumscribed radius of the class footprint (center to farthest corner, not half the width). The free corridor for the axle is x ∈ [0.246, 1.754], y ∈ [0.246, 1.254].
- Escape rule, replanning only: if the robot's current cell is inflated (a new obstacle detected close by, an obstacle position shifted by association, or path-tracking deviation, since line-of-sight paths run along the edge of the inflated area), the planner may cross **inflated** cells, never raw obstacle cells, at extra cost until it reaches a free cell. Every use is logged.
- Dijkstra with 8 neighbours and no corner cutting (A* later).
- Paths simplified by line of sight.
- Obstacles are discovered during the run. Two detections of the same class within ~20 cm are the same obstacle. Revisit the 20 cm with the Day 5 error curve (about 2–3σ at d_max), or one obstacle may be split into two. Conversely, two real same-class obstacles closer than the radius merge into one, so test layouts keep them farther apart (Day 7 check).
- The robot stops and replans only when the remaining path is blocked.
- "Blocked" uses hysteresis: paths are planned with the full inflation (24.6 cm + footprint radius), but the remaining path counts as blocked only if it enters the obstacle inflated **without** the 3 cm margin (21.6 cm + footprint radius). Line-of-sight paths run along the inflated edge, so without hysteresis every small shift from association would trigger a stop and replan. The check runs for new obstacles and for position updates.

**Camera**
- Logitech C920 at 1280 × 720, pointing horizontally, lens 54.5 mm above the floor and 1 cm behind the front.
- The detector's bboxes are in model-input pixels (e.g. 160 × 160). They are mapped back to the 1280 × 720 frame with the inverse of the impulse's resize mode before any geometry or filter. Use `get_features_from_image_auto_studio_settings`, which applies the same resize mode as the Studio. It expects RGB (it packs channel 0 as red, and the SDK's own examples convert first) while OpenCV frames are BGR, so the frame goes through `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)` before it; boxes are drawn on the BGR frame.
- The resize mode is chosen before training (Day 4). With "Fit shortest axis" (center crop) the model only sees the central 720 × 720 px, so the horizontal FOV drops from ~70° to ~43°. "Squash" keeps the full FOV but roughly halves the horizontal resolution.
- Distance is estimated two ways: (a) `Z = k/h` with one k per class, and (b) floor homography from the bottom edge of the bbox. The method is chosen from measured error.
- Obstacle position, without intrinsics, with the camera at C = (0.17, 0) in the axle frame:
  - the floor homography maps the bottom-center pixel of the bbox to a floor point P in the axle frame. The **bearing always comes from it** and is measured from the camera: u = (P − C)/|P − C|, at angle β from the optical axis;
  - (b) puts the front face at F = P;
  - (a) gives the **depth** Z along the optical axis, not the distance along the ray (pinhole: h = f·H/Z), so F = C + Z·(1, tan β). k is fitted against the camera → front-face depth, i.e. the taped axle → front-face distance minus 0.17 m;
  - the obstacle is placed at F + (depth/2)·u. This is the **footprint center**, which the inflation assumes.
- Detections are dropped beyond d_max (0.7 m of depth Z initially), when the bbox touches the image bottom, or when the position falls outside the arena. They need 3 consecutive frames to count.
- Detections are ignored while the pose state is ROTATE, because frame timestamp latency becomes a large bearing error while turning.

## Pin map (wiring: `docs/diagrama-ligacoes.svg`)

| Function | Pins |
|---|---|
| Left motor (TB6612 channel A) | PWM D6, IN1 D7, IN2 D8 |
| Right motor (channel B) | PWM D9, IN1 D10, IN2 D11 |
| Left encoder | A = D2 (PB3), B = D4 (PA12) |
| Right encoder | A = D3 (PB0), B = D5 (PA11) |

- In the diagram, Motor 1 is the left motor (channel A, encoder on D2/D4) and Motor 2 the right one (channel B, encoder on D3/D5).
- STBY is hardwired to 3.3 V, so there is no software control. The TB6612 has 200 kΩ pull-downs on IN1/IN2/PWM, so the motors coast while the STM32 is in reset or being flashed.
- A Zephyr fatal error halts the STM32 without a reset ("Halting system"), so the PWM timers keep driving at the last duty, and the heartbeat watchdog, which runs on the STM32 itself, cannot stop them. The battery switch is the emergency stop.
- D6 (PB1, TIM3_CH4) and D9 (PB8, TIM4_CH3) are PWM pins on different timers, both at 500 Hz by default (see Architecture).
- The four encoder pins are on distinct EXTI lines, so all four can be used as interrupts (`CHANGE` maps to `GPIO_INT_EDGE_BOTH`). Configure them with `INPUT_PULLUP`: it is harmless for push-pull outputs and needed if the encoder outputs are open-collector.
- Encoders are powered at 3.3 V. The UNO Q is powered by a USB-C power bank; the motors run from a 3S LiPo with a shared ground.

## Current code state

The repository is a cleaned scaffold. The raw code from the earlier App Lab experiments is archived outside the repo in `../TCC_Artifacts/applab_raw_code/`.

- **`sketch/sketch.ino`:** the Day 1 minimal app. `ping`, `hb` and `set_path` are registered with `provide_safe` and follow the command queue rule (`set_path` validates 2–64 values inside the arena, copies them under a mutex and queues a command; a newer `set_path` makes a still-queued older one stale). `loop()` runs the 20 ms tick (`micros()`, `next += 20000`; more than one period late resyncs and counts an overrun). Each tick drains the queue and scans the bridge stack (emergency: short brake, refuse `set_path`, report once); every 25 ticks it sends `diag` and `tick` (lateness, measured dt, tick body time, longest pass outside `loop()`), every 500 ticks `tick_hist` (lateness histogram since boot), plus `threads`, `path_rx` (an order-sensitive checksum of the applied path) and `hook` (any pass outside `loop()` above 3 ms, with the handler calls per thread meanwhile). The motor pins are only set to coast at boot and to short brake on the emergency; there is no PWM yet. The old motor demo used the `TB6612FNG_XCR` library, which was dropped: it raises small speed commands up to its minimum speed (`setMinSpeed`), which interferes with the PI loop, and its standby pin is unused here anyway. Do not bring it back; the plan is an in-house driver.
- **`sketch/sketch.yaml`:** what `arduino-app-cli app new` generates on the board (0.13.0: one `arduino:zephyr` platform with no version and an empty `libraries:` key) plus `fqbn: arduino:zephyr:unoq` (board id `unoq` in the platform's `boards.txt`) and `- dir: libraries/Arduino_RouterBridge` under `libraries:`. `app start` leaves it unchanged. On current platforms (≥ 0.55) `Arduino_RouterBridge` and its dependencies (`Arduino_RPClite`, `MsgPack`, `DebugLog`, `ArxContainer`, `ArxTypeTraits`) come with the platform: the core includes `Arduino_RouterBridge.h` in every sketch, arduino-cli adds the latest release of each platform library when the profile's platform has no version, and `arduino-app-cli app start` removes an index entry for `Arduino_RouterBridge` from `sketch.yaml`. Day 1 keeps what App Lab generates and adds two things: `fqbn: arduino:zephyr:unoq` (only the PC build reads it; the board compiles with the platform's FQBN) and the `dir:` entry for the patched Bridge copy (see Bridge limits). `app start` prints the library versions and paths it used ("Used library …").
- **Freezing the board's versions.** Until the experiments end there is no `arduino-app-cli system update`, no `apt upgrade` and no board update offered by App Lab. `system update` upgrades the board's `arduino-*` apt packages (`arduino-app-cli` among them) with `apt-get install --only-upgrade` (arduino-app-cli `internal/update`), so a plain `apt upgrade` upgrades them too. Any update the board needs happens at the start of Day 1, before anything is recorded. Not updating keeps the platform, but not the other platform libraries: with the platform unpinned, every build takes the latest release of each platform library in the board's library index (arduino-cli `commands/instances.go`), and that index is also refreshed by `arduino-app-cli system init` and whenever a library is added to any app in App Lab (if the index is older than 10 min). `Arduino_RouterBridge` is the exception, since the patched copy pins it. So Day 1 records the "Used library …" lines in `docs/board-versions.txt`, and `deploy.sh` compares the lines that `app start` prints with that file and stops the app if any differ.
- **`python/main.py`:** the Day 1 minimal app. It registers the notification handlers (which only append to the per-run logs `*_app_{diag,events,tick,tickhist,hook}.csv`), then a mission thread retries `ping` until the MCU answers, starts the 5 Hz `hb` thread and runs the `set_path` size test once. `python/run_log.py` opens the per-run CSV logs (UTC time, like the board and the container; exclusive create; line-buffered), tested in `tests/test_run_log.py` (`pyproject.toml` sets `pythonpath = ["python"]` for pytest). The earlier capture + MJPEG version is in commit `b34ea46`; Day 5 rebuilds the capture following the frame rules above. `app.yaml` keeps both local bricks for Days 3–5.
- **`bricks/opencv_camera_handler`:** locks the C920 controls through raw V4L2 ioctls, because `v4l2-ctl` is not available inside the app container. Focus only sticks after the stream has run for about 8 s (`open(warm_up_seconds=8)`), and it is set last. The device path comes from the `VIDEO_DEVICE` env var or defaults to `/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920-video-index0`.
- **`bricks/flask_video_webui`:** a Flask MJPEG server on port 8888, which is the port declared in `app.yaml`.
- **`models/`:** holds the Edge Impulse `.eim` model; only `.gitkeep` is tracked. `*.eim` files are gitignored (re-download them from Edge Impulse), but `deploy.sh` must copy `models/` to the board. Its `--delete` removes from the board any model that is not in the PC's `models/`, so every model lives on the PC first.

## Development workflow

- Edit on the PC.
- Deploy over Wi-Fi with rsync + ssh through the ssh alias `unoq` (`~/.ssh/config` on the PC: user `arduino`, key auth, `192.168.1.24` since 2026-10-10; if the IP changes, only the alias changes). `rsync` is not part of the board image: it was installed on Day 1 with `apt-get install rsync` (one new package, nothing upgraded).
- The app lives in `/home/arduino/ArduinoApps/agv` on the board (app id `user:agv`; arduino-app-cli names a user app after its folder under the Apps Directory). The older App Lab apps were backed up to `../TCC_Artifacts/board_backup_20261010/`; `agv-motors-test` is the old motor demo with no limits and must not be started.
- The sketch is compiled and flashed to the STM32 by the board itself when the app starts.
- Inside the app container, the app folder is mounted at `/app` and the host `/dev` at `/dev`. Files written under `/app` persist in the app folder on the board, so per-run logs go to `/app/logs/`.
- Per-run log files:
  - Each file name is unique: date and time plus mode and parameters (e.g. `20261012-143005_step_L25.csv`), never a fixed name that a later run would overwrite.
  - Every row is flushed when it is written (`buffering=1` or `flush()`). On `app stop`, `App.run` turns SIGTERM into an exception only in the main thread (`arduino.app_utils` `app.py`), so files written from other threads (the Bridge dispatcher's `pose` handler, the mission thread) are never closed, and unflushed rows would be lost.
- `deploy.sh` stops the running app (`app start` refuses while another app runs), syncs only `app.yaml`, `python/`, `sketch/`, `bricks/` and `models/`, then starts the app, checks its "Board platform: …" and "Used library …" lines against `docs/board-versions.txt` once that file exists (see Current code state), checks that the `Arduino_RouterBridge` line points to `sketch/libraries/` once the patched copy exists (both checks only warn before then) and follows its logs (`--no-follow` skips that). Any `rsync --delete` leaves `logs/` and `.cache/` on the board untouched: `.cache/` holds the app's Python venv (`/app/.cache/.venv`) and the sketch build cache, and wiping it reinstalls everything on the next start.
- Data for the thesis lives in the repo, in `data/<day>/` (e.g. `data/day1/`). `deploy.sh pull <day>`:
  - stops the app first, so no file is copied while it is still being written (`--remove-source-files` would delete a half-copied file and the rest of that run would be lost), and leaves it stopped; the next `deploy.sh` starts it;
  - `app stop` also resets the STM32 (arduino-app-cli `stopAppWithCmd`): the motors coast and the sketch restarts idle, but a run in progress and any data still in the STM32's RAM are lost, so pull only between runs;
  - copies the files in `/app/logs/` there with `--ignore-existing`, so a file already in `data/<day>/` is never overwritten, and only then deletes them on the board (`rsync --remove-source-files`), so the board's storage does not fill up. A file skipped by `--ignore-existing` is not deleted (checked with rsync 3.5.1), so it stays on the board and `pull` lists whatever is left in `logs/` at the end.
- The PC-only analysis scripts live in `analysis/`, read `data/<day>/` and write plots to `data/<day>/plots/`.
- `rsync -a` keeps the executable bit that the `.eim` needs: the Edge Impulse runner refuses a model that is not executable, so `chmod +x` it after downloading.
- Do not use Zed remote-SSH: its `~/.zed_server` filled the board's storage. Do not use ADB either, because the board is mounted in the robot.
- Board-side commands (from `docs/logs/`):

  ```bash
  arduino-app-cli app list
  arduino-app-cli app start <path|user:name>
  arduino-app-cli app logs <path> --follow
  arduino-app-cli app stop <path>
  arduino-app-cli system cleanup
  ```

- **`docs/board-versions.txt`:** the board's software versions recorded on Day 1 (arduino-app-cli 0.13.0, arduino-router 0.10.0, `arduino:zephyr` 1.0.0, container image `python-apps-base:0.12.0` with `arduino_app_bricks` 0.12.0) and, at the end, the "Board platform: …" and "Used library …" lines that `deploy.sh` compares on every deploy.
- Planned but **not created yet**: `analysis/` (Day 1), and pytest suites for odometry, grid, planner, simplification, association and homography (Days 2 and 4).

## Local Python environment (PC only)

`pyproject.toml`, `uv.lock`, `.python-version` and `.venv/` exist only for the editor and for running tests on the PC. They are never deployed.

```bash
uv sync                 # create/update .venv (Python 3.13)
uv run pytest           # run all tests
uv run pytest path/to/test_file.py::test_name   # run a single test
uvx basedpyright python bricks                  # same type check Zed shows
```

- **`python/requirements.txt` is what the board installs.** When a runtime dependency is added, put it in `requirements.txt` **and** in the `dev` group of `pyproject.toml`.
  - **Exception: OpenCV is never in `requirements.txt`.** The container image (`ghcr.io/arduino/app-bricks/python-apps-base:0.12.0`) ships `opencv-python-headless` 4.13.0+1ddb20b, a local build that is not on PyPI, and pins it with `UV_CONSTRAINT=/etc/uv-constraints.txt`. The app venv is created with `--system-site-packages`, so it sees that build. Any `opencv-python-headless` line makes `uv pip install -r requirements.txt` unsatisfiable, and `/run.sh` ignores the failure: the app starts without any of its requirements and retries on every start. OpenCV stays only in the `dev` group of `pyproject.toml`.
- **Versions match the board container:** Python 3.13 (3.13.14 in the image) and `opencv-python-headless` 4.13.x.
- **`arduino.app_utils`** comes from `arduino_app_bricks`, which is not on PyPI. It is installed from GitHub, pinned in `pyproject.toml` to the release the board's container runs: `tag = "release/0.12.0"` (tags are `bricks/<version>` from 0.13.0 on, `release/<version>` for older releases).
- **Editor support for the sketch (clangd in Zed):**
  - the PC has `arduino-cli` 1.5.1 in `~/.local/bin` and `arduino:zephyr@1.0.0`, the board's version (toolchain `arm-zephyr-eabi` 1.0.1, GCC 14.3.0);
  - `arduino-cli compile --only-compilation-database --build-path build sketch`, run from the repo root, writes `build/compile_commands.json` (gitignored, never inside `sketch/`, which `deploy.sh` syncs to the board). It uses the `sketch.yaml` profile, so the include path points to the patched Bridge copy. Run it again after changing `sketch.yaml` or the libraries;
  - the database has no entry for `sketch.ino` (it compiles a generated `build/sketch/sketch.ino.cpp`), so clangd borrows that entry's flags. `.clangd` adds `-xc++ -std=gnu++17 -include Arduino.h` for `.ino` files, because arduino-cli prepends `#include <Arduino.h>` itself;
  - `.zed/settings.json` passes `--query-driver` for `arm-zephyr-eabi-g*` to Zed's bundled clangd (without `path`, Zed keeps its own clangd and still applies `arguments`: Zed 1.23.2 `crates/project/src/lsp_store.rs`);
  - checked with `clangd --check` on a probe `.ino`: Arduino, Zephyr and Bridge symbols resolve with 0 errors, and an undeclared symbol is reported.
- **basedpyright config:** everything is under `[tool.basedpyright]`, with `extraPaths = ["bricks"]` so brick imports resolve and `typeCheckingMode = "standard"`. Do not add a separate `[tool.pyright]` section: basedpyright then ignores one of the two.
- **`edge_impulse_linux` (1.2.2) declares no dependencies**, but its `__init__` imports `audio.py`, which needs `pyaudio` and `six`. `six` is in `requirements.txt`.
  - Do **not** add `pyaudio`: it has no Linux wheels, and building it on the board fails, so the app's dependency install would break.
  - The detector module stubs it before the import (this works on the PC and on the board):

    ```python
    sys.modules.setdefault("pyaudio", types.ModuleType("pyaudio"))  # audio code is never used
    import edge_impulse_linux.image
    ```
- **Imports that fail when run on the PC** (not in the editor):
  - `arduino.app_utils` needs `watchdog`.
  - Tests should target pure-Python modules that do not import it.
