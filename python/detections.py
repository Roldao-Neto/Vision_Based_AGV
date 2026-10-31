import math
from dataclasses import dataclass
from typing import NamedTuple

from planner import ASSOCIATION_RADIUS_M

F_PX = 907.0
CX_PX = 640.0
CY_PX = 360.0
FRAME_W_PX = 1280
SIDE_MARGIN_PX = 2 * 1280 / 160  # two model pixels: a box this close to a side is cut off by it
MIN_VISIBLE = 0.75  # a side-cut box showing less of the base width than this has no usable edges
CAMERA_X_M = 0.17  # lens, ahead of the axle
LENS_HEIGHT_M = 0.0545  # above the floor
D_MAX_M = 0.7  # farthest depth Z kept
CONFIRM_FRAMES = 3  # consecutive inference frames at the same spot before a sighting counts

# (height, depth) of each class: 152 mm is three of the four cones (the other is 154 mm), 70 mm the widest base
CLASS_SIZE_M = {"cone": (0.152, 0.070)}

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
    cut: bool = False  # cut off by a side of the frame, too much to place


def locate(label: str, x0: float, y0: float, x1: float, y1: float) -> Sighting:
    """A box in 1280 x 720 frame pixels -> its obstacle in the axle frame."""
    height, depth = CLASS_SIZE_M[label]
    z = F_PX * height / (y1 - y0)
    if y1 > CY_PX:
        # Up close the top leaves the frame and h is cut short, so z reads too far. The floor point
        # under the base gives a depth that far away reads much farther than h: the nearer one holds
        z = min(z, F_PX * LENS_HEIGHT_M / (y1 - CY_PX))
    width = F_PX * depth / z
    left, right = x0 <= SIDE_MARGIN_PX, x1 >= FRAME_W_PX - SIDE_MARGIN_PX
    u = (x0 + x1) / 2
    if left != right:  # only the edge inside the frame is real: the center is half a base from it
        u = x1 - width / 2 if left else x0 + width / 2
    cut = left != right and x1 - x0 < MIN_VISIBLE * width
    bearing = math.atan((CX_PX - u) / F_PX)
    fx, fy = CAMERA_X_M + z, z * math.tan(bearing)
    return Sighting(label, z, bearing, fx + depth / 2 * math.cos(bearing), fy + depth / 2 * math.sin(bearing), cut)


def in_view(s: Sighting) -> bool:
    return s.z <= D_MAX_M and not s.cut


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
