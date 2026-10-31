import threading
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from ai_edge_litert.interpreter import Interpreter
from capture import Capture
from detections import Box, Frame

MODELS = Path("/app/models")
LABELS = ("cone",)
THRESHOLD = 0.5
IOU = 0.2
MAX_BOXES = 10


def iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU of box a with each row of b, all (x0, y0, x1, y1)."""
    w = np.clip(np.minimum(a[2], b[:, 2]) - np.maximum(a[0], b[:, 0]), 0, None)
    h = np.clip(np.minimum(a[3], b[:, 3]) - np.maximum(a[1], b[:, 1]), 0, None)
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) - inter
    return inter / np.maximum(union, 1e-9)


def decode(rows: np.ndarray) -> list[Box]:
    """Output rows (xmin, ymin, xmax, ymax, one score per label), normalized, to frame boxes."""
    # Squash resized the whole frame, so normalized coordinates are fractions of 1280 x 720
    xyxy = np.clip(rows[:, :4], 0, 1) * (1280, 720, 1280, 720)
    boxes = []
    for c, label in enumerate(LABELS):
        scores = rows[:, 4 + c]
        order = np.flatnonzero(scores >= THRESHOLD)
        order = order[np.argsort(-scores[order])]
        # Greedy NMS, as the Edge Impulse SDK: drop every box overlapping a kept one by IoU >= IOU
        while order.size:
            i, order = order[0], order[1:]
            boxes.append(Box(label, float(scores[i]), *map(float, xyxy[i])))
            order = order[iou(xyxy[i], xyxy[order]) < IOU]
    return sorted(boxes, key=lambda b: -b.score)[:MAX_BOXES]


class Detector:
    def __init__(self, capture: Capture, event: Callable[[str, object], None], on_frame: Callable[[Frame], None]):
        self._capture = capture
        self._event = event
        self._on_frame = on_frame  # every inferred frame, boxes or not
        self._latest: Frame | None = None

    def latest(self) -> Frame | None:
        """The boxes of the latest frame inferred, with that frame's time, or None before it."""
        return self._latest

    def run(self) -> None:
        try:
            model = next(MODELS.glob("*.tflite"))
            interpreter = Interpreter(model_path=str(model))
            interpreter.allocate_tensors()
            inp = interpreter.get_input_details()[0]
            out = interpreter.get_output_details()[0]
            if inp["dtype"] != np.float32 or out["shape"][-1] != 4 + len(LABELS):
                raise RuntimeError(f"input {inp['dtype']}, output {out['shape']}: expected "
                                   f"float32 and {4 + len(LABELS)} columns for {LABELS}")
        except Exception as e:  # noqa: BLE001
            self._event("detector_error", e)
            return
        _, h, w, _ = inp["shape"]
        self._event("detector_ready", f"{model.name} {w}x{h} {LABELS}")
        while True:
            latest = self._capture.latest()
            if latest is None:
                time.sleep(0.1)
                continue
            frame, t = latest
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            x = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
            interpreter.set_tensor(inp["index"], x[None])
            interpreter.invoke()
            self._latest = Frame(t, decode(interpreter.get_tensor(out["index"])[0]))
            self._on_frame(self._latest)

    def start(self) -> None:
        threading.Thread(target=self.run, name="detector", daemon=True).start()
