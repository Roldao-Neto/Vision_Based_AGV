import threading

from flask import Flask, Response


class Server:
    def __init__(self, port = 8888):
        self.port = port

    def start_simple_video(self, video_function, width = '100%'):

        if(video_function is None):
            raise RuntimeError("No Video Function Detected to Stream in start_simple_video")

        app = Flask(__name__)

        # Expects a function that yields frames
        @app.route('/video_feed')
        def video_feed():
            return Response(video_function(), mimetype='multipart/x-mixed-replace; boundary=frame')

        @app.route('/')
        def index():
            return f"<img src='/video_feed' style='width:{width}'>"

        threading.Thread(target=lambda: app.run(host='0.0.0.0', port=self.port, threaded=True, use_reloader=False),daemon=True).start()
