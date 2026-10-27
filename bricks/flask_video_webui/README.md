# flask_video_webui

A Flask server on port 8888. `Server()` creates the Flask app in `__init__`, so the app registers its own routes on `server.app`; `video(fn)` adds an MJPEG stream at `/video_feed` from a generator of multipart JPEG frames; `start()` runs the server in a daemon thread.
