"""Text commands -> arguments of the MCU call mode(code, p1, p2, p3, p4).

The codes mirror `sketch/src/modes/modes.h`.
"""

IDLE = 0
# 1-3 were the Day 1 identification modes (count, step, ramp) and 4 the wheel PI test (speed)
STRAIGHT = 5
UMBMARK = 6

MODE_NAMES = {STRAIGHT: "straight", UMBMARK: "umbmark"}
END_REASONS = {1: "time", 2: "distance", 3: "command", 4: "emergency", 5: "encoder", 6: "target"}

ModeArgs = tuple[int, int, int, int, int]


def _is_int(word: str) -> bool:
    return word.removeprefix("-").isdigit() # negative sign and checks


def parse(text: str) -> ModeArgs | None:
    match text.split():
        case ["idle"]:
            return (IDLE, 0, 0, 0, 0)
            
        case ["straight", *params] if len(params) == 4 and all(_is_int(p) for p in params):
            v_mm_s, accel_mm_s2, time_ms, dist_mm = (int(p) for p in params)
            return (STRAIGHT, v_mm_s, accel_mm_s2, time_ms, dist_mm)

        case ["umbmark", *params] if len(params) == 4 and all(_is_int(p) for p in params):
            direction, side_mm, v_mm_s, time_ms = (int(p) for p in params)  # direction 1 = CCW, -1 = CW
            return (UMBMARK, direction, side_mm, v_mm_s, time_ms)
            
        case _:
            return None
