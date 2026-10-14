"""Text commands -> arguments of the MCU call mode(code, p1, p2, p3, p4).

The codes mirror `sketch/src/modes/modes.h`.
"""

IDLE = 0
COUNT = 1
STEP = 2
RAMP = 3
SPEED = 4

END_REASONS = {1: "time", 2: "distance", 3: "command", 4: "emergency", 5: "encoder"}

ModeArgs = tuple[int, int, int, int, int]


def _is_int(word: str) -> bool:
    return word.removeprefix("-").isdigit() # negative sign and checks


def parse(text: str) -> ModeArgs | None:
    match text.split():
        case ["count", "start"]:
            return (COUNT, 0, 0, 0, 0)
            
        case ["count", "stop"] | ["idle"]:
            return (IDLE, 0, 0, 0, 0)
            
        case ["step", *params] if len(params) == 4 and all(_is_int(p) for p in params):
            duty_l, duty_r, time_ms, dist_mm = (int(p) for p in params)
            return (STEP, duty_l, duty_r, time_ms, dist_mm)
            
        case ["ramp", *params] if len(params) == 4 and all(_is_int(p) for p in params):
            direction, rate, max_duty, dist_mm = (int(p) for p in params)
            return (RAMP, direction, rate, max_duty, dist_mm)
            
        case ["speed", *params] if len(params) == 4 and all(_is_int(p) for p in params):
            v_mm_s, accel_mm_s2, time_ms, dist_mm = (int(p) for p in params)
            return (SPEED, v_mm_s, accel_mm_s2, time_ms, dist_mm)
            
        case _:
            return None
