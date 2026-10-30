import heapq
import itertools
import math
from dataclasses import dataclass

from arena import Point

CELL_M = 0.025
NX, NY = 80, 60  # 2 x 1.5 m

ROTATION_RADIUS_M = 0.216  # farthest point of the body from the axle: turning in place
HALF_WIDTH_M = 0.12  # the body is 24 cm wide: driving straight past
MARGIN_M = 0.01

# Free corridor for the axle: walls inflated by 22.6 cm, except the wall behind A (x = 0)
X_MAX = 2.0 - ROTATION_RADIUS_M - MARGIN_M  # 1.774
Y_MIN = ROTATION_RADIUS_M + MARGIN_M  # 0.226
Y_MAX = 1.5 - ROTATION_RADIUS_M - MARGIN_M  # 1.274

# Circumscribed radius of each class footprint (center to farthest corner)
FOOTPRINT_RADIUS_M = {"box": math.hypot(0.0802, 0.0802) / 2}  # 80.2 x 80.2 mm base: 56.7 mm

ASSOCIATION_RADIUS_M = 0.20  # same class within this = same obstacle; revisited on Day 5–6

Cell = tuple[int, int]  # (ix, iy)
Grid = list[list[bool]]  # occupied[iy][ix]


@dataclass
class Obstacle:
    label: str
    x: float  # footprint center, m
    y: float
    n: int = 1  # detections averaged into x, y

    def pass_radius(self, margin: float) -> float:
        return HALF_WIDTH_M + margin + FOOTPRINT_RADIUS_M[self.label]

    def turn_radius(self, margin: float) -> float:
        return ROTATION_RADIUS_M + margin + FOOTPRINT_RADIUS_M[self.label]


def associate(obstacles: list[Obstacle], label: str, x: float, y: float) -> Obstacle:
    """Adds one detection to the list: the nearest same-class obstacle within the association
    radius takes the mean of all its detections, otherwise the detection is a new obstacle."""
    near = [o for o in obstacles if o.label == label and math.hypot(o.x - x, o.y - y) <= ASSOCIATION_RADIUS_M]
    if not near:
        obstacles.append(Obstacle(label, x, y))
        return obstacles[-1]
    o = min(near, key=lambda o: math.hypot(o.x - x, o.y - y))
    o.n += 1
    o.x += (x - o.x) / o.n
    o.y += (y - o.y) / o.n
    return o


def in_corridor(p: Point) -> bool:
    return 0.0 <= p[0] <= X_MAX and Y_MIN <= p[1] <= Y_MAX


def build_grid(obstacles: list[Obstacle]) -> Grid:
    return [[_occupied(ix, iy, obstacles) for ix in range(NX)] for iy in range(NY)]


def _occupied(ix: int, iy: int, obstacles: list[Obstacle]) -> bool:
    x0, y0 = ix * CELL_M, iy * CELL_M
    x1, y1 = x0 + CELL_M, y0 + CELL_M
    if x1 > X_MAX or y0 < Y_MIN or y1 > Y_MAX:
        return True
    for o in obstacles:
        # Nearest point of the cell to the obstacle center
        nx, ny = min(max(o.x, x0), x1), min(max(o.y, y0), y1)
        if math.hypot(o.x - nx, o.y - ny) < o.turn_radius(MARGIN_M):
            return True
    return False


def cell_of(p: Point) -> Cell:
    return int(p[0] // CELL_M), int(p[1] // CELL_M)


def cell_center(c: Cell) -> Point:
    return (c[0] + 0.5) * CELL_M, (c[1] + 0.5) * CELL_M


NEIGHBOURS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def astar(grid: Grid, start: Cell, goal: Cell) -> list[Cell] | None:

    def h(c: Cell) -> float:
        dx, dy = abs(c[0] - goal[0]), abs(c[1] - goal[1])
        return dx + dy + (math.sqrt(2) - 2) * min(dx, dy)

    cost = {start: 0.0}
    prev: dict[Cell, Cell] = {}
    heap = [(h(start), start)]
    while heap:
        _, c = heapq.heappop(heap)
        if c == goal:
            path = [goal]
            while path[-1] != start:
                path.append(prev[path[-1]])
            return path[::-1]
        ix, iy = c
        for dx, dy in NEIGHBOURS:
            nx, ny = ix + dx, iy + dy
            if not (0 <= nx < NX and 0 <= ny < NY) or grid[ny][nx]:
                continue
            if dx and dy and (grid[iy][nx] or grid[ny][ix]):  # no corner cutting
                continue
            new = cost[c] + (math.sqrt(2) if dx and dy else 1.0)
            if new < cost.get((nx, ny), math.inf):
                cost[(nx, ny)] = new
                prev[(nx, ny)] = c
                heapq.heappush(heap, (new + h((nx, ny)), (nx, ny)))

    return None


def _segment_distance(p: Point, q: Point, c: Point) -> float:
    dx, dy = q[0] - p[0], q[1] - p[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((c[0] - p[0]) * dx + (c[1] - p[1]) * dy) / length2))
    return math.hypot(p[0] + t * dx - c[0], p[1] + t * dy - c[1])


def _hits(p: Point, q: Point, obstacles: list[Obstacle], margin: float) -> bool:
    return any(_segment_distance(p, q, (o.x, o.y)) < o.pass_radius(margin) for o in obstacles)


def can_turn(p: Point, obstacles: list[Obstacle], margin: float = MARGIN_M) -> bool:
    return all(math.hypot(o.x - p[0], o.y - p[1]) >= o.turn_radius(margin) for o in obstacles)


def visible(p: Point, q: Point, obstacles: list[Obstacle]) -> bool:
    return in_corridor(p) and in_corridor(q) and not _hits(p, q, obstacles, MARGIN_M)


def simplify(points: list[Point], obstacles: list[Obstacle], last_leg: float = 0.0) -> list[Point]:
    goal = points[-1]
    out = [points[0]]
    i = 0
    while i < len(points) - 1:
        i = next((j for j in range(len(points) - 1, i + 1, -1)
                  if (j == len(points) - 1 or math.dist(points[j], goal) >= last_leg)
                  and visible(points[i], points[j], obstacles)), i + 1)
        out.append(points[i])
    return out


def plan(start: Point, goal: Point, obstacles: list[Obstacle], last_leg: float = 0.0) -> list[Point] | None:
    if not (in_corridor(start) and in_corridor(goal) and can_turn(start, obstacles)):
        return None
    grid = build_grid(obstacles)
    s, g = cell_of(start), cell_of(goal)
    if grid[g[1]][g[0]]:
        return None
    grid[s[1]][s[0]] = False
    cells = astar(grid, s, g)
    if cells is None:
        return None
    return simplify([start, *map(cell_center, cells[1:-1]), goal], obstacles, last_leg)[1:]


def blocked(path: list[Point], obstacles: list[Obstacle]) -> bool:
    return (any(_hits(p, q, obstacles, 0.0) for p, q in itertools.pairwise(path))
            or not all(can_turn(w, obstacles, 0.0) for w in path[1:-1]))
