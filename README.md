# Vision-Based AGV

Undergraduate thesis (TCC, Engenharia de Computação, Unifei). A differential-drive robot on an
**Arduino UNO Q** drives from a fixed start A to a fixed goal B in a 2 × 1.5 m arena. It localizes
**only by wheel odometry** and uses a camera to detect obstacles, which it adds to an occupancy grid
before replanning a collision-free path.

**Status:** scaffold. Implementation follows [`docs/ROADMAP.md`](docs/ROADMAP.md).

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

- **STM32U585 (real time):** encoders, PI speed control per wheel, odometry, heading control,
  point-to-point waypoint following.
- **Linux (QRB2210):** camera, Edge Impulse obstacle detector, obstacle distance estimation,
  occupancy grid, Dijkstra path planning, web UI.
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

_To be written on Day 1: PC setup (`uv sync`), deployment to the board, starting the app._

## Calibration

_To be written on Day 2: encoder counts per revolution, mm/tick per wheel, track width, UMBmark._

## Running a mission

_To be written on Day 3: web UI, Bridge messages, logs._

## Obstacle detection

_To be written on Days 4–5: classes and dataset, model, distance method and its error._

## Results

_To be written on Day 7: scenarios S0–S2, arrival and odometry errors, success rate._
