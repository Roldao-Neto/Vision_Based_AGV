import math
from dataclasses import dataclass
from typing import NamedTuple

from planner import ASSOCIATION_RADIUS_M

F_PX = 907.0
CX_PX = 640.0
CY_PX = 360.0
FRAME_H_PX = 720
BOTTOM_MARGIN_PX = 720 / 160  # one model pixel: a box this close to the bottom touches it
CAMERA_X_M = 0.17  # lens, ahead of the axle
LENS_HEIGHT_M = 0.0545  # above the floor
D_MAX_M = 0.7  # farthest depth Z kept
CONFIRM_FRAMES = 3  # consecutive inference frames at the same spot before a sighting counts

# (height, depth) of each class, measured with a caliper (box on Day 4)
CLASS_SIZE_M = {"box": (0.0752, 0.0802)}

ARENA_W_M, ARENA_H_M = 2.0, 1.5


class Box(NamedTuple):
    label: str
    score: float
    x0: float  # 1280 x 720 frame pixels
    y0: float
    x1: float
    y1: float


class Frame(NamedTuple):
    t: float  # the frame's V4L2 buffer time, s (the clock of time.monotonic())
    boxes: list[Box]


@dataclass(frozen=True)
class Sighting:
    label: str
    z: float  # depth of the front face along the optical axis, m
    bearing: float  # from the optical axis, rad, left positive
    x: float  # footprint center in the axle frame, m
    y: float


def locate(label: str, x0: float, y0: float, x1: float, y1: float) -> Sighting:
    """A box in 1280 x 720 frame pixels -> its obstacle in the axle frame."""
    height, depth = CLASS_SIZE_M[label]
    if y1 >= FRAME_H_PX - BOTTOM_MARGIN_PX and y0 < CY_PX:
        # Bottom cut off: the top edge, above the lens, gives the depth. With the top cut off too
        # (y0 = 0) this is 0.052 m for the box, the farthest it can be
        z = F_PX * (height - LENS_HEIGHT_M) / (CY_PX - y0)
    else:
        z = F_PX * height / (y1 - y0)
    bearing = math.atan((CX_PX - (x0 + x1) / 2) / F_PX)
    fx, fy = CAMERA_X_M + z, z * math.tan(bearing)
    return Sighting(label, z, bearing, fx + depth / 2 * math.cos(bearing), fy + depth / 2 * math.sin(bearing))


def in_view(s: Sighting) -> bool:
    return s.z <= D_MAX_M


def to_arena(x: float, y: float, theta: float, s: Sighting) -> tuple[float, float]:
    c, si = math.cos(theta), math.sin(theta)
    return x + c * s.x - si * s.y, y + si * s.x + c * s.y


def in_arena(p: tuple[float, float]) -> bool:
    return 0.0 <= p[0] <= ARENA_W_M and 0.0 <= p[1] <= ARENA_H_M


Seen = tuple[str, float, float]  # label, footprint center in the arena frame (m)


class Confirm:
    def __init__(self) -> None:
        self._last: list[tuple[Seen, int]] = []

    def update(self, seen: list[Seen]) -> list[Seen]:
        counts = []
        for label, x, y in seen:
            near = [n for (l, px, py), n in self._last
                    if l == label and math.hypot(px - x, py - y) <= ASSOCIATION_RADIUS_M]
            counts.append(((label, x, y), max(near, default=0) + 1))
        self._last = counts
        return [s for s, n in counts if n >= CONFIRM_FRAMES]
