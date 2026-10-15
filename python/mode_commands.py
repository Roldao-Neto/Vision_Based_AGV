"""Text commands -> arguments of the MCU call mode(code, p1, p2, p3, p4).

The codes mirror `sketch/src/modes/modes.h`.
"""

IDLE = 0
SPEED = 4  # 1-3 were the Day 1 identification modes (count, step, ramp)

END_REASONS = {1: "time", 2: "distance", 3: "command", 4: "emergency", 5: "encoder"}

ModeArgs = tuple[int, int, int, int, int]


def _is_int(word: str) -> bool:
    return word.removeprefix("-").isdigit() # negative sign and checks


def parse(text: str) -> ModeArgs | None:
    match text.split():
        case ["idle"]:
            return (IDLE, 0, 0, 0, 0)
            
        case ["speed", *params] if len(params) == 4 and all(_is_int(p) for p in params):
            v_mm_s, accel_mm_s2, time_ms, dist_mm = (int(p) for p in params)
            return (SPEED, v_mm_s, accel_mm_s2, time_ms, dist_mm)
            
        case _:
            return None
