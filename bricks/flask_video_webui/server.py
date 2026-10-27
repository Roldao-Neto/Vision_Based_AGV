import threading
from collections.abc import Callable, Iterator

from flask import Flask, Response


class Server:
    def __init__(self, port: int = 8888):
        self.port = port
        self.app = Flask(__name__)

    def video(self, video_function: Callable[[], Iterator[bytes]], route: str = "/video_feed") -> None:
        self.app.add_url_rule(
            route, "video_feed",
            lambda: Response(video_function(), mimetype="multipart/x-mixed-replace; boundary=frame"),
        )

    def start(self) -> None:
        threading.Thread(
            target=lambda: self.app.run(host="0.0.0.0", port=self.port, threaded=True, use_reloader=False),
            name="flask", daemon=True,
        ).start()
