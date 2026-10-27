"""Text commands -> MCU calls (method, args).

The mode codes and end reasons mirror `sketch/src/modes/modes.h`.
"""

IDLE = 0
# 1-3 were the Day 1 identification modes (count, step, ramp), 4 the wheel PI test (speed) and
# 5-6 the Day 2 calibration modes (straight, umbmark)
PATH = 7

MODE_NAMES = {PATH: "path"}
# 1 (time) and 2 (overshoot guard) were the Day 2 limits
END_REASONS = {3: "command", 4: "emergency", 5: "encoder", 6: "target", 7: "heartbeat"}

McuCall = tuple[str, tuple[object, ...]]


def _is_int(word: str) -> bool:
    return word.removeprefix("-").isdigit()  # negative sign and checks


def parse(text: str) -> McuCall | None:
    words = text.split()
    if not all(_is_int(w) for w in words[1:]):
        return None
    params = [int(w) for w in words[1:]]
    match words[:1], params:
        case ["idle"], []:
            return ("mode", (IDLE, 0, 0, 0, 0))

        case ["stop"], []:  # pauses the run; idle ends it
            return ("stop", ())

        case ["reset_pose"], [x_mm, y_mm, theta_mrad]:  # axle pose
            return ("reset_pose", (x_mm, y_mm, theta_mrad))

        case ["path"], [path_id, *xy_mm] if xy_mm and len(xy_mm) % 2 == 0:  # absolute axle waypoints
            return ("set_path", (path_id, xy_mm))

        case _:
            return None
