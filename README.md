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

| Path | Contents |
|---|---|
| `sketch/` | STM32 firmware (Arduino sketch, Zephyr core) |
| `python/` | Linux application |
| `bricks/` | Local App bricks: camera handler and Flask video UI |
| `models/` | Edge Impulse model as a float32 `.tflite` (not versioned) |
| `results/` | Logs and screen recordings of the S0–S2 runs |

## Setup

Everything is edited on the PC and deployed to the board over Wi-Fi. The board compiles and flashes the sketch itself when the app starts.

**PC.** Requirements: [uv](https://docs.astral.sh/uv/), `ssh` and `rsync`.

```bash
uv sync
uvx basedpyright python bricks
```

**Board.** An ssh alias `unoq` and `rsync` installed on the board. The board's software stays frozen (no `system update`, no `apt upgrade`); the versions are in `docs/board-versions.txt`.

```bash
./deploy.sh               # stop the running app, sync, start this app, check versions, follow its logs
./deploy.sh --no-follow   # the same, without following the logs
```

## Running a mission

1. Deploy and put the robot on A: the rear reference point on the mark, facing B.
2. Open `http://<board-ip>:8888/`. Whenever the robot is put back on A by hand, or an obstacle is moved, press **Reset at A**: it sets the odometry to A again and clears the obstacles.
3. Press **Start**. The robot plans a path to B around the obstacles it has seen. When the camera finds an obstacle on the remaining path, it stops with a ramp, replans and goes on.
4. **Stop** ends the mission with a ramped stop.

Commands can also be sent to the running app with `./deploy.sh run <command>`; see `deploy.sh` and `python/command_file.py`.

## Logs

Each app start writes CSV files with unique names to `/app/logs/` on the board: events, poses, paths, detections, obstacles, STM32 health and the samples of each run.

```bash
./deploy.sh pull dayX     # stop the app and move the board's logs into data/dayX/
```

`pull` resets the STM32, so pull only between runs.

## Calibration

Odometry uses one distance per encoder count for each wheel and the track, calibrated with 5 straight A→B runs and UMBmark (Borenstein and Feng 1996, 5 CW + 5 CCW 1 m squares). The values are in `sketch/src/config/config.h`.

Result, before → after (5 runs each): UMBmark E_max,syst 41.9 → 8.1 mm; straight A→B, error along the line −26.7 ± 2.2 → 0.5 ± 0.4 mm and to the side +16.1 ± 3.0 → +4.3 ± 4.7 mm. Data: branch `day2` (tag `day2-final`).

## Obstacle detection and planning

- **Class:** `cone`, four cones 68.6–70.0 mm across at the base: three are 152 mm high and one is 154 mm.
- **Model:** Edge Impulse YOLO-Pro, 160 × 160 RGB, run as a float32 TFLite network with LiteRT on the board, ~5 inferences/s.
- **Position:** from geometry alone, with no camera calibration: the box height gives the distance and its position in the image gives the bearing. A detection counts within 0.7 m of depth, inside the arena, after 3 consecutive frames at the same spot, and not while the robot rotates.
- **Planning:** A* on a 2.5 cm occupancy grid, then line-of-sight simplification. The robot's axle keeps 16.5 cm from a cone's center to drive past it and 26.1 cm to turn in place, including a 1 cm margin.
- **Known limitations:**
  - The 1 cm margin leaves little room for the error in a cone's position.
  - An obstacle is never removed during a session, so moving one needs Reset at A.
  - If the robot stops too close to a cone to turn in place, the planner finds no path and the mission fails.
  - After a detour the robot stops with its center on B, facing along the last segment.

## Results

The robot was tested with 10 recorded runs in each of three scenarios. Each run was classified by watching it in the arena: a success has the robot's center within the limit radius of B and no contact with a cone. Nothing was measured with tape, so these are success rates, not arrival errors.

| Scenario | Obstacles | Successes | Time to arrive (successful runs) | Runs with a replan |
|---|---|---|---|---|
| S0 | none | 10/10 | 7.20–7.29 s | 0 |
| S1 | 1 cone between A and B | 9/10 | 9.23–12.76 s | 3 |
| S2 | 2–4 cones forcing a detour | 9/10 | 9.44–14.08 s | 5, including the failed run |
| **Total** | | **28/30** | | |

The exact 95% confidence interval for the overall success rate is 78–99%.

**The two failures:**

- **S1, run 5, contact with the cone.** The robot reached B but touched the cone while passing it. The estimated gap between body and cone was only about 1.6 cm, so a small error in the cone's position was enough.
- **S2, run 10, no path.** This layout was built on purpose to mislead the robot, and it failed the same way in all 3 attempts. While passing the first cone, the robot found another one that made its next waypoint unusable, and it stopped at once, 17–23 cm from the first cone. That is less than the 26.1 cm needed to turn in place, so the planner found no path. The stop was safe, with no contact.
