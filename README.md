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
- **Linux (QRB2210):** camera, Edge Impulse obstacle detector, obstacle distance estimation, occupancy grid, Dijkstra path planning, web UI.
- **Bridge:** the STM32 streams its pose; Linux sends absolute (x, y) waypoints.

## Repository layout

| Path | Contents |
|---|---|
| `sketch/` | STM32 firmware (Arduino sketch, Zephyr core) |
| `python/` | Linux application |
| `bricks/` | Local App bricks: camera handler and Flask video UI |
| `models/` | Edge Impulse `.eim` model (not versioned) |
| `docs/` | Roadmap, wiring diagram, development logs |

## Setup and running

Everything is edited on the PC and deployed to the board over Wi-Fi. The board compiles and flashes the sketch itself when the app starts.

### PC

Requirements: [uv](https://docs.astral.sh/uv/), `ssh`, `rsync` and, for the native C++ tests, `g++`.

```bash
uv sync                          # .venv with Python 3.13 and the dev + analysis groups
uv run pytest                    # Python tests and the native C++ tests of sketch/src (skipped without g++)
uvx basedpyright python bricks   # type check
```

The `.venv`, `pyproject.toml` and `uv.lock` exist only for the editor, the tests and `analysis/`. The board installs `python/requirements.txt` inside its own container; OpenCV comes with the container image and is never listed there.

### Board access

- An ssh alias `unoq` in `~/.ssh/config` (user `arduino`, key authentication). Another alias can be used with `BOARD=<alias> ./deploy.sh …`.
- `rsync` installed on the board (`sudo apt-get install rsync`).
- The board's software is frozen until the experiments are done: no `arduino-app-cli system update`, no `apt upgrade`, no board update from App Lab. The versions are in `docs/board-versions.txt`.

### Deploy and run

```bash
./deploy.sh               # stop the running app, sync, start this app, check versions, follow its logs
./deploy.sh --no-follow   # the same, without following the logs
```

At start, Python discards any command left in `cmd/` while the app was stopped, retries `ping` until the STM32 answers, and then sends the 5 Hz heartbeat.

**Commands** go to the running app with `./deploy.sh run <command>`, which prints the last lines of the events log (the ack):

| Command | What it does |
|---|---|
| `idle` | end the current mode |
| `straight <v_mm_s> <accel_mm_s2> <time_ms> <dist_mm>` | drive `dist_mm` along the start heading (`v` negative = backward) and stop there, heading held by the heading PI |
| `umbmark <dir> <side_mm> <v_mm_s> <time_ms>` | UMBmark square, `dir` 1 = CCW, −1 = CW: four legs, a 90° turn in place after each |

Both end with a `<mode>_end` event (the odometry poses at the start and the end) and a `*_<mode>_<id>_….csv` with one sample per 20 ms tick.

**Logs.** Each run writes CSV files with unique names to `/app/logs/` on the board. Between runs:

```bash
./deploy.sh pull day1     # stop the app and move the board's logs into data/day1/
```

`pull` leaves the app stopped, and stopping the app resets the STM32, so pull only between runs; the next `./deploy.sh` starts it again. Files already in `data/<day>/` are never overwritten. The PC-only analysis scripts in `analysis/` read `data/<day>/` and write plots to `data/<day>/plots/`.

## Calibration

Odometry uses one distance per encoder count for each wheel and the track b (`kOdometry` in `sketch/src/config/config.h`). Each value comes from a measurement:

| Parameter | How it is obtained | Value |
|---|---|---|
| Encoder counts per wheel revolution | 3 runs of 10 turns by hand (Day 1, `count` mode) | 1319.7 (left), 1319.8 (right), ±0.5; 1319.75 used for both |
| Nominal distance per count | π · 67.5 mm / 1319.75 | 0.16068 mm |
| Scale Es (mean distance per count) | 5 straight runs of 1403 mm, A→B, real distance (tape) ÷ odometry distance | 0.98103 → 0.157632 mm per count |
| Wheel ratio Ed, track error Eb | UMBmark (Borenstein and Feng 1996): 5 CW + 5 CCW 1 m squares, real − odometry end position, the paper's Eqs. 4.20–4.27 | Ed = 1.00176, Eb = 0.99575 |
| Distance per count, left / right | Es-corrected mean × c_L / c_R = 2/(Ed + 1), 2/(1/Ed + 1) | 0.157493 mm / 0.157771 mm |
| Track b | 0.217 m × Eb | 216.08 mm |

Result, before → after (5 runs each): UMBmark E_max,syst 41.9 → 8.1 mm (below 3·SEM, so a second correction would not help); straight A→B, error along the line −26.7 ± 2.2 → 0.5 ± 0.4 mm and to the side +16.1 ± 3.0 → +4.3 ± 4.7 mm.

Every real pose is measured from a tape cross on the floor: the robot's reference point along and across the line, and a front point on its centreline across the line, which gives the heading. The analysis is `analysis/day2_bench.py` (method and data format in `docs/logs/day2-bench.md`).

## Running a mission

_To be written on Day 3: web UI, Bridge messages, logs._

## Obstacle detection

_To be written on Days 4–5: classes and dataset, model, distance method and its error._

## Results

_To be written on Day 7: scenarios S0–S2, arrival and odometry errors, success rate._
