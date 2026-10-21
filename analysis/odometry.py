"""Reference odometry (PC only): the firmware's midpoint integration in float64.

Same formula as sketch/src/odometry (docs/ROADMAP.md, Day 2):
d = (dL + dR)/2, dθ = (dR − dL)/b, x += d·cos(θ + dθ/2), y += d·sin(θ + dθ/2), θ += dθ,
with dL and dR the count deltas times each wheel's m/count. θ is not wrapped.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Pose:
    x: float  # m, axle midpoint
    y: float  # m
    theta: float  # rad, counter-clockwise, not wrapped


def step(pose: Pose, dcount_l: int, dcount_r: int, m_per_count_l: float, m_per_count_r: float, track: float) -> Pose:
    dl = dcount_l * m_per_count_l
    dr = dcount_r * m_per_count_r
    d = 0.5 * (dl + dr)
    dtheta = (dr - dl) / track
    heading = pose.theta + 0.5 * dtheta
    return Pose(pose.x + d * math.cos(heading), pose.y + d * math.sin(heading), pose.theta + dtheta)


def integrate(
    counts_l: Sequence[int],
    counts_r: Sequence[int],
    m_per_count_l: float,
    m_per_count_r: float,
    track: float,
    pose0: Pose,
) -> list[Pose]:
    """Poses at each sample of absolute counts, the first one being pose0."""
    poses = [pose0]
    for i in range(1, len(counts_l)):
        poses.append(
            step(poses[-1], counts_l[i] - counts_l[i - 1], counts_r[i] - counts_r[i - 1], m_per_count_l, m_per_count_r, track)
        )
    return poses
