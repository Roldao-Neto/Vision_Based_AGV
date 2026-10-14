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
| `count start`, `count stop` | count encoder edges while the wheels are turned by hand |
| `idle` | end the current mode |
| `step <duty_l> <duty_r> <time_ms> <dist_mm>` | open-loop duty step, duties in thousandths (±300) |
| `ramp <dir> <rate> <max_duty> <dist_mm>` | slow open-loop duty ramp (`dir` ±1, rate in thousandths per second) |
| `speed <v_mm_s> <accel_mm_s2> <time_ms> <dist_mm>` | closed-loop speed test of the wheel PI (`accel` 0 = step) |

**Logs.** Each run writes CSV files with unique names to `/app/logs/` on the board. Between runs:

```bash
./deploy.sh pull day1     # stop the app and move the board's logs into data/day1/
```

`pull` leaves the app stopped, and stopping the app resets the STM32, so pull only between runs; the next `./deploy.sh` starts it again. Files already in `data/<day>/` are never overwritten. The PC-only analysis scripts in `analysis/` read `data/<day>/` and write plots to `data/<day>/plots/`.

## Calibration

_To be written on Day 2: encoder counts per revolution, mm/tick per wheel, track width, UMBmark._

## Running a mission

_To be written on Day 3: web UI, Bridge messages, logs._

## Obstacle detection

_To be written on Days 4–5: classes and dataset, model, distance method and its error._

## Results

_To be written on Day 7: scenarios S0–S2, arrival and odometry errors, success rate._
