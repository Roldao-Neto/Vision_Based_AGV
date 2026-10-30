import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from arena import (
    AXLE_TO_CENTER_M,
    B_CENTER,
    START_AXLE,
    START_HEADING,
    Point,
    axle_to_center,
    pull_back_goal,
    to_mm,
)
from detections import Confirm, Frame, Seen, in_arena, in_view, locate, to_arena
from mcu_commands import END_REASONS, IDLE
from planner import CELL_M, MARGIN_M, Obstacle, associate, blocked, build_grid, plan

IDLE_STATE = 0  # follower phases in the pose notification
ROTATE = 1
ARRIVED = 3
END_TARGET = 6

POSE_HISTORY = 50  # 2 s of poses at 25 Hz, to match frames inferred ~0.2 s after they were taken
MATCH_MAX_S = 0.1  # a frame with no pose this close in time is dropped
RESET_SETTLE_S = 0.1  # frames taken before reset_pose took effect are dropped
# Shortest last segment planned: the 7 cm pull-back leaves at least 5 cm to drive (a planner
# waypoint 4 cm from B left nothing to pull back, and 5 Starts did nothing, Day 5–6)
LAST_LEG_M = AXLE_TO_CENTER_M + 0.05


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
LogDetection = Callable[..., None]  # one row per box, see telemetry.DETECTIONS_HEADER
LogObstacles = Callable[[list[Obstacle]], None]  # the list after every change


class Mission:
    def __init__(self, call: Call, event: Event, log_path: LogPath, log_detection: LogDetection,
                 log_obstacles: LogObstacles, clock: Callable[[], float] = time.monotonic):
        self._call = call
        self._event = event
        self._log_path = log_path
        self._log_detection = log_detection
        self._log_obstacles = log_obstacles
        self._clock = clock
        self._inbox: queue.Queue[str] = queue.Queue()  # "start" / "abort" / "reset" from the UI or cmd/
        self._run_ends: queue.Queue[tuple[int, int]] = queue.Queue()  # (path_id, reason)
        self._frames: queue.Queue[Frame] = queue.Queue()
        self._lock = threading.Lock()
        self._poses: deque[Pose] = deque(maxlen=POSE_HISTORY)
        self._confirm = Confirm()
        self._frames_after = 0.0  # frames taken before this monotonic time are dropped
        self.status = "idle"  # idle, running, stopping (for a replan), aborting, arrived, aborted, failed
        self.path_id = 0
        self.path_start: Point = START_AXLE
        self.path: list[Point] = []
        self._started = 0.0
        self.obstacles: list[Obstacle] = []
        self.grid = build_grid(self.obstacles)

    # Any thread

    def post(self, name: str) -> None:
        self._inbox.put(name)

    def on_pose(self, pose: Pose) -> None:
        with self._lock:
            self._poses.append(pose)

    def on_run_end(self, path_id: int, reason: int) -> None:
        self._run_ends.put((path_id, reason))

    def on_frame(self, frame: Frame) -> None:
        self._frames.put(frame)

    def snapshot(self) -> dict[str, object]:
        """For the UI: the axle pose, and the robot center it is drawn around; the grid as one
        string per row from y = 0 ("#" occupied), and each obstacle's two inflated radii."""
        with self._lock:
            pose = self._poses[-1] if self._poses else None
            state: dict[str, object] = {
                "status": self.status,
                "path_id": self.path_id,
                "path": [list(self.path_start), *map(list, self.path)],
                "pose": None,
                "cell": CELL_M,
                "grid": ["".join("#" if c else "." for c in row) for row in self.grid],
                "obstacles": [{"label": o.label, "x": o.x, "y": o.y, "n": o.n, "r_plan": o.radius(MARGIN_M),
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
            elif name == "reset":
                self._reset()
        while not self._frames.empty():
            self._see(self._frames.get())
        self._check_progress()

    def _latest_pose(self) -> Pose | None:
        with self._lock:
            return self._poses[-1] if self._poses else None

    def _set_status(self, status: str) -> None:
        with self._lock:
            self.status = status

    def _send(self, method: str, *args: object) -> object:
        try:
            return self._call(method, *args)
        except Exception as e:  # noqa: BLE001  # a Bridge error fails the mission, not the thread
            return e

    def _fail(self, why: str, end_run: bool = False) -> None:
        """end_run: a run is open (paused for a replan), so idle ends it on the STM32."""
        self._set_status("failed")
        self._event("mission_failed", f"path_id={self.path_id} {why}")
        if end_run:
            ack = self._send("mode", IDLE, 0, 0, 0, 0)
            if ack is not True:
                self._event("mission_error", f"fail: idle ack={ack!r}")

    def _reset_pose(self) -> object:
        start_mm = to_mm([START_AXLE])
        ack = self._send("reset_pose", *start_mm, round(1000 * START_HEADING))
        if ack is True:
            self._frames_after = self._clock() + RESET_SETTLE_S
        return ack

    def _reset(self) -> None:
        if self.status in ("running", "stopping", "aborting"):
            self._event("mission_rejected", f"reset while {self.status}")
            return
        ack = self._reset_pose()
        if ack is not True:
            self._event("mission_error", f"reset: reset_pose ack={ack!r}")
            return
        with self._lock:
            self.obstacles = []
            self.grid = build_grid(self.obstacles)
            self.path_start, self.path = START_AXLE, []
            self.status = "idle"
        self._confirm = Confirm()
        self._log_obstacles(self.obstacles)
        self._event("mission_reset", f"start_axle_mm={to_mm([START_AXLE])}")

    def _start(self) -> None:
        if self.status in ("running", "stopping", "aborting"):
            self._event("mission_rejected", f"start while {self.status}")
            return
        pose = self._latest_pose()
        path_id = max(pose.path_id if pose is not None else 0, self.path_id) + 1
        ack = self._reset_pose()
        if ack is not True:
            self._fail(f"reset_pose ack={ack!r}")
            return
        path = self._plan(START_AXLE)
        if path is None:
            self._fail(f"no path from the start with {len(self.obstacles)} obstacles")
            return
        if self._send_path(path_id, START_AXLE, path):
            self._started = self._clock()
            self._set_status("running")
            self._event("mission_start", f"path_id={path_id} obstacles={len(self.obstacles)} "
                        f"path_mm={to_mm(self.path)}")

    def _plan(self, start: Point) -> list[Point] | None:
        """Waypoints from start to B, the last pulled back 7 cm so the center stops on B, or None."""
        waypoints = plan(start, B_CENTER, self.obstacles, LAST_LEG_M)
        if waypoints is None:
            return None
        try:
            return pull_back_goal(start, waypoints)
        except ValueError as e:  # the last segment is not longer than the 7 cm pull-back
            self._event("mission_error", f"plan: {e}")
            return None

    def _send_path(self, path_id: int, start: Point, path: list[Point]) -> bool:
        path_mm = to_mm(path)
        ack = self._send("set_path", path_id, path_mm)
        self._log_path(path_id, path_mm, ack)
        with self._lock:
            self.path_id = path_id
            self.path_start, self.path = start, path
        if ack is not True:
            self._fail(f"set_path ack={ack!r}", end_run=self.status == "stopping")
            return False
        return True

    def _abort(self) -> None:
        if self.status not in ("running", "stopping"):
            self._event("mission_rejected", f"abort while {self.status}")
            return
        ack = self._send("mode", IDLE, 0, 0, 0, 0)
        if ack is not True:
            self._event("mission_error", f"abort: idle ack={ack!r}")
            return
        self._set_status("aborting")
        self._event("mission_abort", f"path_id={self.path_id}")

    # Detections

    def _pose_at(self, t: float) -> Pose | None:
        with self._lock:
            pose = min(self._poses, key=lambda p: abs(p.t_linux - t), default=None)
        return pose if pose is not None and abs(pose.t_linux - t) <= MATCH_MAX_S else None

    def _see(self, frame: Frame) -> None:
        """Places the frame's boxes in the arena, confirms them and updates the obstacles."""
        if frame.t < self._frames_after:
            return
        pose = self._pose_at(frame.t)
        seen: list[Seen] = []
        rows = []
        for b in frame.boxes:
            s = locate(b.label, b.x0, b.y0, b.x1, b.y1)
            p = to_arena(pose.x, pose.y, pose.theta, s) if pose is not None else (float("nan"), float("nan"))
            if pose is None:
                outcome = "no_pose"
            elif pose.state == ROTATE:
                outcome = "rotate"  # frame latency is a large bearing error while turning
            elif not in_view(s):
                outcome = "far"
            elif not in_arena(p):
                outcome = "outside"
            else:
                outcome = "seen"
                seen.append((b.label, *p))
            rows.append([b, s, p, outcome])
        # A frame with nothing usable (rotating included) breaks every count
        confirmed = self._confirm.update(seen)
        changed = False
        for label, x, y in confirmed:
            with self._lock:
                associate(self.obstacles, label, x, y)
            changed = True
            for r in rows:
                if r[3] == "seen" and (r[0].label, *r[2]) == (label, x, y):
                    r[3] = "confirmed"
        for b, s, p, outcome in rows:
            self._log_detection(frame.t, pose, b, s, p, outcome)
        if changed:
            with self._lock:
                self.grid = build_grid(self.obstacles)
            self._log_obstacles(self.obstacles)
            self._check_blocked()

    def _remaining(self, pose: Pose) -> list[Point]:
        """The current axle position, then the waypoints of the current path not reached yet."""
        wp = pose.wp_idx if pose.path_id == self.path_id else 0
        return [(pose.x, pose.y), *self.path[wp:]]

    def _check_blocked(self) -> None:
        pose = self._latest_pose()
        if self.status != "running" or pose is None or not blocked(self._remaining(pose), self.obstacles):
            return
        ack = self._send("stop")
        if ack is not True:
            self._fail(f"stop ack={ack!r}", end_run=True)
            return
        self._set_status("stopping")
        self._event("mission_blocked", f"path_id={self.path_id} at=({pose.x:.3f}, {pose.y:.3f}) "
                    f"obstacles={[(o.label, round(o.x, 3), round(o.y, 3), o.n) for o in self.obstacles]}")

    def _replan(self, pose: Pose) -> None:
        start = (pose.x, pose.y)
        path = self._plan(start)
        if path is None:
            self._fail(f"no path from ({pose.x:.3f}, {pose.y:.3f}) with {len(self.obstacles)} obstacles",
                       end_run=True)
            return
        if self._send_path(self.path_id + 1, start, path):
            self._set_status("running")
            self._event("mission_replan", f"path_id={self.path_id} from=({pose.x:.3f}, {pose.y:.3f}) "
                        f"path_mm={to_mm(self.path)}")

    # Progress

    def _check_progress(self) -> None:
        while not self._run_ends.empty():
            path_id, reason = self._run_ends.get()
            if path_id != self.path_id or self.status not in ("running", "stopping", "aborting"):
                continue
            if reason == END_TARGET:
                self._arrived("run_end")
            elif self.status == "aborting":
                self._set_status("aborted")
                self._event("mission_aborted", f"path_id={path_id} after={self._clock() - self._started:.2f}s")
            else:
                self._fail(f"run_end reason={END_REASONS.get(reason, reason)}")
        pose = self._latest_pose()
        if pose is None or pose.path_id != self.path_id:
            return  # progress of an older path is ignored
        if self.status in ("running", "stopping") and pose.state == ARRIVED and pose.wp_idx == len(self.path) - 1:
            self._arrived("pose")
        elif self.status == "stopping" and pose.state == IDLE_STATE:
            self._replan(pose)

    def _arrived(self, seen_by: str) -> None:
        self._set_status("arrived")
        pose = self._latest_pose()
        where = "" if pose is None else f" axle=({pose.x:.4f}, {pose.y:.4f}) theta={pose.theta:.4f}"
        self._event("mission_arrived",
                    f"path_id={self.path_id} after={self._clock() - self._started:.2f}s seen_by={seen_by}{where}")
