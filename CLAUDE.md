# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Undergraduate thesis (TCC, Unifei): a differential-drive AGV on an **Arduino UNO Q** that drives from a fixed start A to a fixed goal B, avoiding obstacles it discovers with a camera.

- **Localization is wheel odometry only.** ArUco markers, solvePnP, camera intrinsics and vision/odometry fusion were dropped. Do not reintroduce them.
- Vision is used only to detect obstacles and estimate where they are.
- The day-by-day plan is in `docs/ROADMAP.md`.

## Working rules

- The user writes in Portuguese. Reply in Portuguese.
- Code identifiers **and comments** are in English.
- Any doubt, ambiguity or conflict with the agreed design below must be asked, never assumed.

## Architecture

The UNO Q has two processors linked by the **Bridge** (RPC through the `arduino-router` service on Linux):

- **STM32U585 (`sketch/`, Arduino sketch on the Zephyr core) — real time, 20 ms tick:**
  - x4 quadrature encoder interrupts;
  - PI speed loop per wheel (first-order model + feedforward);
  - odometry;
  - heading PID;
  - point-to-point controller: rotate in place, then drive straight with the heading re-aimed at the waypoint.
  The STM32 owns the robot pose.
- **QRB2210 Debian (`python/`, `bricks/`, `app.yaml`):** camera, Edge Impulse detector, obstacle distance, occupancy grid, Dijkstra, path simplification, mission manager, Flask UI, CSV logs.

Bridge contract:

| Direction | Message | Content |
|---|---|---|
| STM32 → Linux | `notify("pose", t_ms, x, y, theta, state)` | 20 Hz |
| Linux → STM32 | `call("set_path", id, [x1, y1, ...])` | up to 32 **absolute** waypoints, acked; never relative commands |
| Linux → STM32 | `call("stop")`, `call("mode", ...)` | `mode` switches mission and calibration modes (`count`, `step`, `straight`, `spin`, `umbmark`) |
| Linux → STM32 | `notify("hb")` | 5 Hz heartbeat; STM32 stops after 1 s without it (except in calibration modes) |

`t_ms` is used to match each camera frame with the pose at that moment. It is the **STM32 clock**, not synchronized with Linux, so it must never be compared directly with Linux timestamps:
- Python stores the Linux monotonic receive time of every `pose`.
- It estimates the clock offset as the minimum of `(receive − t_ms)`, i.e. the least-delayed message.
- It converts poses to the Linux clock with that offset.
- Frames are timestamped right after `Camera.read()` on the Linux monotonic clock and matched to the pose closest in time.

## Frames and constants

**Arena and goal**
- Arena: 2 × 1.5 m inside the MDF walls. Origin at the inner wall corner, x along the 2 m side, θ counter-clockwise, SI units.
- Robot center: A = (0.22, 0.745), B = (1.77, 0.745), θ0 = 0.

**Reference point**
- The STM32 tracks the **axle midpoint**, which is 7 cm behind the robot center.
- Python converts between center and axle at the boundaries. Goal B is converted along the direction of the last path segment.

**Robot geometry**
- Track b ≈ 21.7 cm, still to be refined by calibration.
- Wheel Ø 67.5 mm. Motors JGB37-520 12 V 333 rpm; encoder counts per revolution are not known yet and are measured in `count` mode.
- Body 22 × 24 cm, axle 4 cm from the rear, steel-ball caster at the front.
- The farthest point from the axle is 21.6 cm away. This is the rotation sweep radius used for obstacle inflation.

**Motion**
- 0.25 m/s cruise, 0.5 m/s², rotation up to 90 °/s.
- A rotation ends when the heading error is below 3°.
- Arrival tolerance is 5 cm, and the robot stops at every waypoint.

**Planner**
- Occupancy grid of 5 cm cells (40 × 30).
- Walls inflated by 15 cm. Obstacles inflated by 24.6 cm plus half of the class size.
- Dijkstra with 8 neighbours and no corner cutting (A* later).
- Paths simplified by line of sight.
- Obstacles are discovered during the run. Two detections of the same class within ~20 cm are the same obstacle.
- The robot stops and replans only when the remaining path is blocked.

**Camera**
- Logitech C920 at 1280 × 720, pointing horizontally, lens 54.5 mm above the floor and 1 cm behind the front.
- Distance is estimated two ways: (a) `d = k/h` with one k per class, and (b) floor homography from the bottom edge of the bbox. The method is chosen from measured error.
- Detections are dropped beyond d_max (0.7 m initially) or when the bbox touches the image bottom, and need 3 consecutive frames to count.

## Pin map (wiring: `docs/diagrama-ligacoes.svg`)

| Function | Pins |
|---|---|
| Left motor (TB6612 channel A) | PWM D6, IN1 D7, IN2 D8 |
| Right motor (channel B) | PWM D9, IN1 D10, IN2 D11 |
| Left encoder | A = D2 (PB3), B = D4 (PA12) |
| Right encoder | A = D3 (PB0), B = D5 (PA11) |

- STBY is hardwired to 3.3 V, so there is no software control.
- The four encoder pins are on distinct EXTI lines, so all four can be used as interrupts.
- Encoders are powered at 3.3 V. The UNO Q is powered by a USB-C power bank; the motors run from a 3S LiPo with a shared ground.

## Current code state

The repository is a cleaned scaffold. The raw code from the earlier App Lab experiments is archived outside the repo in `../TCC_Artifacts/applab_raw_code/`.

- **`sketch/sketch.ino`:** empty `setup()`/`loop()`. The old motor demo used the `TB6612FNG_XCR` library, which was dropped: it raises small speed commands up to its minimum speed (`setMinSpeed`), which interferes with the PI loop, and its standby pin is unused here anyway. Do not bring it back; the plan is an in-house driver.
- **`python/main.py`:** only captures frames and streams MJPEG, then calls `App.run()`. No inference yet.
- **`bricks/opencv_camera_handler`:** locks the C920 controls through raw V4L2 ioctls, because `v4l2-ctl` is not available inside the app container. Focus only sticks after the stream has run for about 8 s (`open(warm_up_seconds=8)`), and it is set last. The device path comes from the `VIDEO_DEVICE` env var or defaults to `/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920-video-index0`.
- **`bricks/flask_video_webui`:** a Flask MJPEG server on port 8888, which is the port declared in `app.yaml`.
- **`models/`:** currently empty.

## Development workflow

- Edit on the PC.
- Deploy over Wi-Fi with rsync + ssh to `arduino@<board IP>` (it was `192.168.0.105` during setup).
- The sketch is compiled and flashed to the STM32 by the board itself when the app starts.
- Do not use Zed remote-SSH: its `~/.zed_server` filled the board's storage. Do not use ADB either, because the board is mounted in the robot.
- Board-side commands (from `docs/logs/`):

  ```bash
  arduino-app-cli app list
  arduino-app-cli app start <path|user:name>
  arduino-app-cli app logs <path> --follow
  arduino-app-cli app stop <path>
  arduino-app-cli system cleanup
  ```

- Planned but **not created yet**: `deploy.sh` (Day 1) and pytest suites for odometry, grid, planner, simplification, association and homography (Days 2 and 4).

## Local Python environment (PC only)

`pyproject.toml`, `uv.lock`, `.python-version` and `.venv/` exist only for the editor and for running tests on the PC. They are never deployed.

```bash
uv sync                 # create/update .venv (Python 3.13)
uv run pytest           # run all tests
uv run pytest path/to/test_file.py::test_name   # run a single test
uvx basedpyright python bricks                  # same type check Zed shows
```

- **`python/requirements.txt` is what the board installs.** When a runtime dependency is added, put it in `requirements.txt` **and** in the `dev` group of `pyproject.toml`.
- **Versions match the board container:** Python 3.13 and `opencv-python-headless` 4.13.x.
- **`arduino.app_utils`** comes from `arduino_app_bricks`, which is not on PyPI. It is installed from GitHub and pinned by `uv.lock`.
- **`.clangd`** only makes clangd parse `.ino` as C++. Arduino and Zephyr headers will not resolve until the Day 1 `compile_commands.json` setup is done.
- **basedpyright config:** everything is under `[tool.basedpyright]`, with `extraPaths = ["bricks"]` so brick imports resolve and `typeCheckingMode = "standard"`. Do not add a separate `[tool.pyright]` section: basedpyright then ignores one of the two.
- **Imports that fail when run on the PC** (not in the editor):
  - `edge_impulse_linux` needs `pyaudio`, which it does not declare. Check on the board on Day 5 whether `requirements.txt` needs it too.
  - `arduino.app_utils` needs `watchdog`.
  - Tests should target pure-Python modules that do not import these.
