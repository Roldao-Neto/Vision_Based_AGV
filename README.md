# Vision-Based AGV

Undergraduate thesis (TCC, Engenharia de Computação, Unifei). A differential-drive robot on an **Arduino UNO Q** drives from a fixed start A to a fixed goal B in a 2 × 1.5 m arena. It localizes **only by wheel odometry** and uses a camera to detect obstacles, which it adds to an occupancy grid before replanning a collision-free path.

## Hardware

| Part | Model |
|---|---|
| Board | Arduino UNO Q: Qualcomm QRB2210 (Debian Linux) + STM32U585 (Zephyr), linked by the Bridge |
| Motors | 2 × JGB37-520, 12 V, 333 rpm, Hall quadrature encoders |
| Wheels | Ø 67.5 mm, track width ≈ 21.7 cm, steel-ball caster at the front |
| Motor driver | TB6612FNG |
| Camera | Logitech C920 (USB), 1280 × 720, mounted horizontally 54.5 mm above the floor |
| Power | 3S LiPo for the motors; USB-C power bank for the board |

Wiring: [`docs/diagrama-ligacoes.svg`](docs/diagrama-ligacoes.svg).

## Architecture

- **STM32U585 (real time):** encoders, PI speed control per wheel, odometry, heading control, point-to-point waypoint following.
- **Linux (QRB2210):** camera, Edge Impulse obstacle detector, obstacle distance estimation, occupancy grid, A* path planning, mission manager, web UI.
- **Bridge:**

| Direction | Message | What it does |
|---|---|---|
| Linux → STM32 | `set_path(id, [x1_mm, y1_mm, …])` | follow 1–32 absolute axle waypoints, stopping at each |
| Linux → STM32 | `reset_pose(x_mm, y_mm, θ_mrad)` | set the odometry pose of the axle |
| Linux → STM32 | `stop()` / `mode(0, …)` | ramped stop that pauses the run for a replan / ends it |
| STM32 → Linux | `pose(t_ms, x, y, θ, state, path_id, wp_idx)` | 25 Hz; state 0 IDLE, 1 ROTATE, 2 DRIVE, 3 ARRIVED |

## Repository layout

| Path | Contents |
|---|---|
| `sketch/` | STM32 firmware (Arduino sketch, Zephyr core) |
| `python/` | Linux application |
| `bricks/` | Local App bricks: camera handler and Flask video UI |
| `models/` | Edge Impulse model as a float32 `.tflite` (not versioned) |
| `analysis/` | PC-only analysis scripts; they read `data/<day>/` and write `data/<day>/plots/` |
| `docs/` | Roadmap, wiring diagram, development logs |

## Setup

Everything is edited on the PC and deployed to the board over Wi-Fi. The board compiles and flashes the sketch itself when the app starts.

**PC.** Requirements: [uv](https://docs.astral.sh/uv/), `ssh` and `rsync`.

```bash
uv sync
uvx basedpyright python bricks
```

**Board.** An ssh alias `unoq` and `rsync` installed on the board. The board's software stays frozen until the experiments are done (no `system update`, no `apt upgrade`); the versions are in `docs/board-versions.txt`.

```bash
./deploy.sh               # stop the running app, sync, start this app, check versions, follow its logs
./deploy.sh --no-follow   # the same, without following the logs
```

## Running a mission

1. Deploy and put the robot on A: the rear reference point on the mark, facing B. On start the app sets the odometry to A.
2. Open `http://<board-ip>:8888/`. Whenever the robot is put back on A by hand, or an obstacle is moved, press **Reset at A**: it sets the odometry to A again and clears the obstacles.
3. Press **Start**. The mission plans a path to B around the obstacles already seen, sends it and waits for ARRIVED. When the camera finds an obstacle on the remaining path, the robot stops with a ramp, replans from there and goes on. The page draws the arena, the grid, the obstacles with their inflations, the path, the live pose and the camera with each detection.
4. **Stop** ends the mission with a ramped stop.

**Manual commands** go to the running app with `./deploy.sh run <command>`, which prints the ack:

| Command | What it does |
|---|---|
| `reset_pose <x_mm> <y_mm> <theta_mrad>` | set the axle pose; at A: `reset_pose 178 745 0` |
| `path <id> <x1_mm> <y1_mm> …` | `set_path` |
| `stop` | ramped stop, pauses the run |
| `idle` | ramped stop, ends the run |
| `start`, `abort`, `reset` | the Start, Stop and Reset at A buttons |

A **run** lasts from its first `set_path` to the goal or a failure, replans included, and is recorded tick by tick.

## Logs

Each app start writes a set of CSV files with unique names to `/app/logs/` on the board:

| File | Contents |
|---|---|
| `*_app_events.csv` | commands, acks, `mission_*` events, the end of every run |
| `*_app_pose.csv` | every pose, with the Linux clock offset |
| `*_app_paths.csv` | every `set_path` sent, with its ack |
| `*_app_detections.csv` | every detected box: the pose matched to its frame, distance, bearing, position in the arena and what happened to it |
| `*_app_obstacles.csv` | the obstacle list after every change |
| `*_app_status.csv`, `*_app_hook.csv` | STM32 health |
| `*_path.csv`, `*_path_<record>_paths<n>.csv` | one row per run, and each run's samples (one per 20 ms tick) |

```bash
./deploy.sh pull dayX     # stop the app and move the board's logs into data/dayX/
```

`pull` resets the STM32, so pull only between runs. Files already in `data/<day>/` are never overwritten.

## Calibration

Odometry uses one distance per encoder count for each wheel and the track b (`kOdometry` in `sketch/src/config/config.h`): the scale Es from 5 straight A→B runs, then the wheel ratio Ed and the track error Eb from UMBmark (Borenstein and Feng 1996, 5 CW + 5 CCW 1 m squares).

| Parameter | Value |
|---|---|
| Encoder counts per wheel revolution | 1319.75 (both wheels) |
| Es / Ed / Eb | 0.98103 / 1.00176 / 0.99575 |
| Distance per count, left / right | 0.157493 mm / 0.157771 mm |
| Track b | 216.08 mm |

Result, before → after (5 runs each): UMBmark E_max,syst 41.9 → 8.1 mm; straight A→B, error along the line −26.7 ± 2.2 → 0.5 ± 0.4 mm and to the side +16.1 ± 3.0 → +4.3 ± 4.7 mm. Method and data: `docs/logs/day2-bench.md` and branch `day2` (tag `day2-final`).

## Obstacle detection

- **Resize mode:** "Squash". The whole 1280 × 720 frame is resized to the model input, so the detector sees the camera's full horizontal FOV.

- **Classes:** 
  - `box`, a red cube 80.2 × 80.2 mm at the base and 75.2 mm high.
  - **TODO**

- **Model:** Edge Impulse YOLO-Pro, 160 × 160 RGB, run as a float32 TFLite network with LiteRT on the board, ~5 inferences/s.

- **Distance and position, from geometry alone** (no camera calibration, nothing fitted): a pinhole camera pointing horizontally, 54.5 mm above the floor, with f = 907 px at 1280 × 720 from the Logitech spec (78° diagonal). The depth of the obstacle's front face is `Z = f·H/h` (H the class height, h the box height in pixels); when the box is cut by the image bottom (closer than ~0.14 m), it comes from the top edge instead, `Z = f·(H − 0.0545)/(360 − y_top)`. The bearing comes from the box's bottom middle, and the obstacle is placed at the center of its footprint. Detections count within d_max = 0.7 m of depth, inside the arena, after 3 consecutive frames at the same spot, and not while the robot rotates; each frame is matched to the pose at the moment it was taken. Checked by placing the box around the arena and comparing the grid with it: they match almost exactly.

- **Known limitations:** the depth resolution is the model's (one model pixel of box height is ~3 cm at 0.7 m); an obstacle is never removed during a session, so moving one needs Reset at A; a box closer than its inflation to the robot at A means no path, and the robot does not move; after a detour the robot stops with its center on B but facing along the last segment.

- **Interim model (box only, plus background images):** 449 images, 166 with the box and 283 of background only; 352 for training (71 of them for validation) and 97 for testing. On the test set: mAP@[IoU=50] 1.000, mAP@[IoU=0.50:0.95] 0.804, recall 0.829; small (distant) boxes are the weakest, mAP 0.754. These figures will be replaced by those of the final model with all classes.

## Results

_To be written on Day 7: scenarios S0–S2, arrival and odometry errors, success rate._
