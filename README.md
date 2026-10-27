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
- **Linux (QRB2210):** camera, Edge Impulse obstacle detector, obstacle distance estimation, occupancy grid, Dijkstra path planning, mission manager, web UI.
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
| `models/` | Edge Impulse `.eim` model (not versioned) |
| `tests/` | Python tests and native C++ tests of the pure firmware modules |
| `analysis/` | PC-only analysis scripts; they read `data/<day>/` and write `data/<day>/plots/` |
| `docs/` | Roadmap, wiring diagram, development logs |

## Setup

Everything is edited on the PC and deployed to the board over Wi-Fi. The board compiles and flashes the sketch itself when the app starts.

**PC.** Requirements: [uv](https://docs.astral.sh/uv/), `ssh`, `rsync` and, for the native C++ tests, `g++`.

```bash
uv sync
uv run pytest
uvx basedpyright python bricks
```

**Board.** An ssh alias `unoq` and `rsync` installed on the board. The board's software stays frozen until the experiments are done (no `system update`, no `apt upgrade`); the versions are in `docs/board-versions.txt`.

```bash
./deploy.sh               # stop the running app, sync, start this app, check versions, follow its logs
./deploy.sh --no-follow   # the same, without following the logs
```

## Running a mission

1. Deploy and put the robot on A: the rear reference point on the mark, facing B.
2. Open `http://<board-ip>:8888/` and press **Start**. The mission sets the odometry to the start pose, sends the path to B and waits for ARRIVED. The page draws the arena, the path and the live pose.
3. **Stop** ends the mission with a ramped stop.

**Frames.** The STM32 tracks the axle midpoint, 7 cm behind the robot center, and every waypoint is in axle coordinates. The start axle is (0.178, 0.745), and the last waypoint is pulled back 7 cm so the **center** stops on B.

**Manual commands** go to the running app with `./deploy.sh run <command>`, which prints the ack:

| Command | What it does |
|---|---|
| `reset_pose <x_mm> <y_mm> <theta_mrad>` | set the axle pose; at A: `reset_pose 178 745 0` |
| `path <id> <x1_mm> <y1_mm> …` | `set_path` |
| `stop` | ramped stop, pauses the run |
| `idle` | ramped stop, ends the run |

A **run** lasts from its first `set_path` to the goal or a failure, replans included, and is recorded tick by tick.

## Logs

Each app start writes a set of CSV files with unique names to `/app/logs/` on the board:

| File | Contents |
|---|---|
| `*_app_events.csv` | commands, acks, `mission_*` events, the end of every run |
| `*_app_pose.csv` | every pose, with the Linux clock offset |
| `*_app_paths.csv` | every `set_path` sent, with its ack |
| `*_app_status.csv`, `*_app_hook.csv` | STM32 health |
| `*_path.csv`, `*_path_<record>_paths<n>.csv` | one row per run, and each run's samples (one per 20 ms tick) |

```bash
./deploy.sh pull day3     # stop the app and move the board's logs into data/day3/
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

_To be written on Days 4–5: classes and dataset, model, distance method and its error._

## Results

_To be written on Day 7: scenarios S0–S2, arrival and odometry errors, success rate._
