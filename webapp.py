from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from typing import Dict, List
from urllib.parse import unquote

from replay import validate_replay


class ReplayRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, replays_dir: str, static_dir: str, **kwargs) -> None:
        self.replays_dir = replays_dir
        self.static_dir = static_dir
        super().__init__(*args, directory=static_dir, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/replays":
            self.handle_replays_list()
            return
        if self.path.startswith("/api/replay/"):
            self.handle_replay_fetch()
            return
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def handle_replays_list(self) -> None:
        files = [
            name
            for name in os.listdir(self.replays_dir)
            if name.endswith(".json") and os.path.isfile(os.path.join(self.replays_dir, name))
        ]
        files.sort()
        self.send_json({"replays": files})

    def handle_replay_fetch(self) -> None:
        name = unquote(self.path.replace("/api/replay/", "", 1))
        if "/" in name or "\\" in name:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid replay name")
            return
        path = os.path.join(self.replays_dir, name)
        if not os.path.isfile(path):
            self.send_error(HTTPStatus.NOT_FOUND, "Replay not found")
            return
        with open(path, "r", encoding="utf-8") as handle:
            replay_data = json.load(handle)
        errors = validate_replay(replay_data)
        if errors:
            replay_data["validation_errors"] = errors
        self.send_json(replay_data)

    def send_json(self, payload: Dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay web server")
    parser.add_argument("--replays-dir", type=str, default="replays", help="Replay folder")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.makedirs(args.replays_dir, exist_ok=True)
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    handler = lambda *handler_args, **handler_kwargs: ReplayRequestHandler(  # noqa: E731
        *handler_args,
        replays_dir=args.replays_dir,
        static_dir=static_dir,
        **handler_kwargs,
    )
    with TCPServer((args.host, args.port), handler) as httpd:
        print(f"Serving on http://{args.host}:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
