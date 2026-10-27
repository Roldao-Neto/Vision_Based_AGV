import fcntl
import os
import struct
import time

import cv2


class Camera:
    """Logitech C920 with every image control locked (exposure, white balance, focus).

    Changing FOCUS, ZOOM or the resolution invalidates the floor homography and
    the per-class k/h distance fits.
    """

    FOCUS = 0
    ZOOM = 100

    # V4L2 ioctls (the same ones v4l2-ctl uses; it is not available in the container)
    _G_CTRL = 0xC008561B
    _S_CTRL = 0xC008561C
    _CID = {  # noqa: RUF012
        "brightness": 0x00980900,
        "contrast": 0x00980901,
        "saturation": 0x00980902,
        "white_balance_automatic": 0x0098090C,
        "gain": 0x00980913,
        "power_line_frequency": 0x00980918,
        "white_balance_temperature": 0x0098091A,
        "sharpness": 0x0098091B,
        "backlight_compensation": 0x0098091C,
        "auto_exposure": 0x009A0901,
        "exposure_time_absolute": 0x009A0902,
        "exposure_dynamic_framerate": 0x009A0903,
        "pan_absolute": 0x009A0908,
        "tilt_absolute": 0x009A0909,
        "focus_absolute": 0x009A090A,
        "focus_automatic_continuous": 0x009A090C,
        "zoom_absolute": 0x009A090D,
    }

    # automatic controls first: while they are on, the manual ones stay 'inactive'
    CONTROLS = [  # noqa: RUF012
        ("focus_automatic_continuous", cv2.CAP_PROP_AUTOFOCUS, 0),
        ("auto_exposure", cv2.CAP_PROP_AUTO_EXPOSURE, 1),
        ("white_balance_automatic", cv2.CAP_PROP_AUTO_WB, 0),
        ("exposure_dynamic_framerate", None, 0),
        ("power_line_frequency", None, 2),
        ("exposure_time_absolute", cv2.CAP_PROP_EXPOSURE, 156),
        ("gain", cv2.CAP_PROP_GAIN, 64),
        ("white_balance_temperature", cv2.CAP_PROP_WB_TEMPERATURE, 4000),
        ("zoom_absolute", cv2.CAP_PROP_ZOOM, ZOOM),
        ("pan_absolute", cv2.CAP_PROP_PAN, 0),
        ("tilt_absolute", cv2.CAP_PROP_TILT, 0),
        ("brightness", cv2.CAP_PROP_BRIGHTNESS, 128),
        ("contrast", cv2.CAP_PROP_CONTRAST, 128),
        ("saturation", cv2.CAP_PROP_SATURATION, 128),
        ("sharpness", cv2.CAP_PROP_SHARPNESS, 128),
        ("backlight_compensation", cv2.CAP_PROP_BACKLIGHT, 0),
    ]

    def __init__(self, device=None, width=1280, height=720):
        self._device = device or os.environ.get(
            "VIDEO_DEVICE", "/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920-video-index0"
        )
        self._width, self._height = width, height
        self._cap = None

    def _ctrl(self, name, value=None):
        """G_CTRL if value is None, otherwise S_CTRL. Returns the value, or None."""
        cid = self._CID.get(name)
        if cid is None:
            return None
        fd = None
        try:
            fd = os.open(self._device, os.O_RDWR)
            if value is None:
                out = fcntl.ioctl(fd, self._G_CTRL, struct.pack("Ii", cid, 0))
                return struct.unpack("Ii", out)[1]
            fcntl.ioctl(fd, self._S_CTRL, struct.pack("Ii", cid, int(value)))
            return int(value)
        except OSError:
            return None
        finally:
            if fd is not None:
                os.close(fd)

    def open(self, warm_up_seconds=8, verbose=False):
        """warm_up_seconds >= 8: on this camera focus_absolute only sticks after the
        stream has been running for a few seconds, and only through OpenCV's cap.set."""
        self._cap = cv2.VideoCapture(self._device, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            raise RuntimeError("[Camera] Failed to open camera")

        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*'MJPG'))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if (w, h) != (self._width, self._height):
            self.release()
            raise RuntimeError(
                f"[Camera] asked {self._width}x{self._height}, got {w}x{h}")

        deadline = time.time() + warm_up_seconds
        while time.time() < deadline:
            self._cap.read()

        for name, prop, value in self.CONTROLS:
            if prop is not None:
                self._cap.set(prop, float(value))
                time.sleep(0.05)
                if self._ctrl(name) == value:
                    if verbose:
                        print(f"  ok {name} = {value}")
                    continue
            self._ctrl(name, value)
            time.sleep(0.05)
            got = self._ctrl(name)
            if verbose:
                print(f"  {'ok' if got == value else '!!'} {name} = {got}")

        # focus last: it is the only control that needs a warm stream
        self._cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        for _ in range(15):
            self._cap.read()
        self._cap.set(cv2.CAP_PROP_FOCUS, float(self.FOCUS))
        for _ in range(15):
            self._cap.read()
        time.sleep(0.6)

        focus = self._ctrl("focus_absolute")
        if focus != self.FOCUS:
            self.release()
            raise RuntimeError(
                f"[Camera] focus lock failed: wanted {self.FOCUS}, got {focus}")
        if verbose:
            print(f"  ok focus_absolute = {focus}")

    def read(self):
        if self._cap is None:
            raise RuntimeError("[Camera] Camera is not opened")
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("[Camera] Failed to read frame")
        return frame

    def release(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
