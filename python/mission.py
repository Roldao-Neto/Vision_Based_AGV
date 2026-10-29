"""Mission manager: A -> B on the STM32's point-to-point controller.

A mission: reset_pose with the start axle pose, set_path to B with the last waypoint pulled
back 7 cm, then wait for ARRIVED on the last wp_idx of that path_id. Abort sends idle, which
ends the run on the STM32. A run_end of the path with any other reason fails the mission.
"""

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from arena import (
    B_CENTER,
    START_AXLE,
    START_HEADING,
    Point,
    axle_to_center,
    pull_back_goal,
    to_mm,
)
from mcu_commands import END_REASONS, IDLE
from planner import CELL_M, MARGIN_M, Obstacle, build_grid

ARRIVED = 3  # follower phase in the pose notification
END_TARGET = 6


@dataclass(frozen=True)
class Pose:
    rx: float  # Linux monotonic receive time, s
    t_ms: int  # STM32 clock
    t_linux: float  # t_ms on the Linux monotonic clock (clock_sync), s: when the pose was sent
    x: float  # axle, m
    y: float
    theta: float  # rad, not wrapped
    state: int  # follower phase: 0 IDLE, 1 ROTATE, 2 DRIVE, 3 ARRIVED
    path_id: int
    wp_idx: int


Call = Callable[..., object]  # Bridge.call(method, *args); raises on a Bridge error
Event = Callable[[str, object], None]
LogPath = Callable[[int, list[int], object], None]  # path_id, waypoints in mm, ack


class Mission:
    def __init__(self, call: Call, event: Event, log_path: LogPath, clock: Callable[[], float] = time.monotonic):
        self._call = call
        self._event = event
        self._log_path = log_path
        self._clock = clock
        self._inbox: queue.Queue[str] = queue.Queue()  # "start" / "abort" from the UI or cmd/
        self._run_ends: queue.Queue[tuple[int, int]] = queue.Queue()  # (path_id, reason)
        self._lock = threading.Lock()
        self._pose: Pose | None = None
        self.status = "idle"  # idle, running, aborting, arrived, aborted, failed
        self.path_id = 0
        self.path: list[Point] = []
        self._started = 0.0
        self.obstacles: list[Obstacle] = []  # discovered during a run, from Day 6
        self.grid = build_grid(self.obstacles)

    # Any thread

    def post(self, name: str) -> None:
        self._inbox.put(name)

    def on_pose(self, pose: Pose) -> None:
        with self._lock:
            self._pose = pose

    def on_run_end(self, path_id: int, reason: int) -> None:
        self._run_ends.put((path_id, reason))

    def snapshot(self) -> dict[str, object]:
        """For the UI: the axle pose, and the robot center it is drawn around; the grid as one
        string per row from y = 0 ("#" occupied), and each obstacle's two inflated radii."""
        with self._lock:
            pose = self._pose
            state: dict[str, object] = {
                "status": self.status,
                "path_id": self.path_id,
                "path": [list(START_AXLE), *map(list, self.path)],
                "pose": None,
                "cell": CELL_M,
                "grid": ["".join("#" if c else "." for c in row) for row in self.grid],
                "obstacles": [{"label": o.label, "x": o.x, "y": o.y, "r_plan": o.radius(MARGIN_M),
                               "r_block": o.radius(0.0)} for o in self.obstacles],
            }
        if pose is not None:
            cx, cy = axle_to_center(pose.x, pose.y, pose.theta)
            state["pose"] = {
                "x": pose.x, "y": pose.y, "center_x": cx, "center_y": cy, "theta": pose.theta,
                "state": pose.state, "path_id": pose.path_id, "wp_idx": pose.wp_idx,
                "age_s": self._clock() - pose.rx,
            }
        return state

    # Mission thread

    def step(self) -> None:
        while not self._inbox.empty():
            name = self._inbox.get()
            if name == "start":
                self._start()
            elif name == "abort":
                self._abort()
        self._check_progress()

    def _set_status(self, status: str) -> None:
        with self._lock:
            self.status = status

    def _send(self, method: str, *args: object) -> object:
        try:
            return self._call(method, *args)
        except Exception as e:  # noqa: BLE001  # a Bridge error fails the mission, not the thread
            return e

    def _fail(self, why: str) -> None:
        self._set_status("failed")
        self._event("mission_failed", f"path_id={self.path_id} {why}")

    def _start(self) -> None:
        if self.status in ("running", "aborting"):
            self._event("mission_rejected", f"start while {self.status}")
            return
        with self._lock:
            last_id = self._pose.path_id if self._pose is not None else 0
        path_id = max(last_id, self.path_id) + 1
        start_mm = to_mm([START_AXLE])
        ack = self._send("reset_pose", *start_mm, int(round(1000 * START_HEADING)))
        if ack is not True:
            self._fail(f"reset_pose {start_mm} ack={ack!r}")
            return
        path = pull_back_goal(START_AXLE, [B_CENTER])
        path_mm = to_mm(path)
        ack = self._send("set_path", path_id, path_mm)
        self._log_path(path_id, path_mm, ack)
        with self._lock:
            self.path_id = path_id
            self.path = path
        if ack is not True:
            self._fail(f"set_path ack={ack!r}")
            return
        self._started = self._clock()
        self._set_status("running")
        self._event("mission_start", f"path_id={path_id} start_axle_mm={start_mm} path_mm={path_mm}")

    def _abort(self) -> None:
        if self.status != "running":
            self._event("mission_rejected", f"abort while {self.status}")
            return
        ack = self._send("mode", IDLE, 0, 0, 0, 0)
        if ack is not True:
            self._event("mission_error", f"abort: idle ack={ack!r}")
            return
        self._set_status("aborting")
        self._event("mission_abort", f"path_id={self.path_id}")

    def _check_progress(self) -> None:
        while not self._run_ends.empty():
            path_id, reason = self._run_ends.get()
            if path_id != self.path_id or self.status not in ("running", "aborting"):
                continue
            if reason == END_TARGET:
                self._arrived("run_end")
            elif self.status == "aborting":
                self._set_status("aborted")
                self._event("mission_aborted", f"path_id={path_id} after={self._clock() - self._started:.2f}s")
            else:
                self._fail(f"run_end reason={END_REASONS.get(reason, reason)}")
        with self._lock:
            pose = self._pose
        if (self.status == "running" and pose is not None and pose.path_id == self.path_id
                and pose.state == ARRIVED and pose.wp_idx == len(self.path) - 1):
            self._arrived("pose")

    def _arrived(self, seen_by: str) -> None:
        self._set_status("arrived")
        with self._lock:
            pose = self._pose
        where = "" if pose is None else f" axle=({pose.x:.4f}, {pose.y:.4f}) theta={pose.theta:.4f}"
        self._event("mission_arrived",
                    f"path_id={self.path_id} after={self._clock() - self._started:.2f}s seen_by={seen_by}{where}")
