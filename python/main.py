import threading
import time

import cv2
from arduino.app_utils import App
from flask_video_webui import Server
from opencv_camera_handler import Camera

cam = Camera()

latest_frame, frame_lock = None, threading.Lock()


def capture_loop():
    global latest_frame
    cam.open(verbose=True)
    while True:
        f = cam.read()
        with frame_lock:
            latest_frame = f
        time.sleep(0.005)


server = Server()


def mjpeg():
    while True:
        with frame_lock:
            f = latest_frame.copy() if latest_frame is not None else None

        if f is None:
            time.sleep(0.05)
            continue

        ok, jpg = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                   + jpg.tobytes() + b'\r\n')

        time.sleep(1 / 30)


server.start_simple_video(video_function=mjpeg)

threading.Thread(target=capture_loop, daemon=True).start()

App.run()
