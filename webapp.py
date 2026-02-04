from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from typing import Dict, List, Optional
from urllib.parse import unquote

from replay import validate_replay
from web_session import GameSession


@dataclass
class SessionStore:
    session: Optional[GameSession] = None
    record_eval_in_replay: bool = False


class ReplayRequestHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args,
        replays_dir: str,
        saves_dir: str,
        static_dir: str,
        session_store: SessionStore,
        **kwargs,
    ) -> None:
        self.replays_dir = replays_dir
        self.saves_dir = saves_dir
        self.static_dir = static_dir
        self.session_store = session_store
        super().__init__(*args, directory=static_dir, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/replays":
            self.handle_replays_list()
            return
        if self.path.startswith("/api/replay/"):
            self.handle_replay_fetch()
            return
        if self.path == "/api/saves":
            self.handle_saves_list()
            return
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/game/new":
            self.handle_game_new()
            return
        if self.path == "/api/game/action":
            self.handle_game_action()
            return
        if self.path == "/api/game/step":
            self.handle_game_step()
            return
        if self.path == "/api/game/pause":
            self.handle_game_pause()
            return
        if self.path == "/api/game/resume":
            self.handle_game_resume()
            return
        if self.path == "/api/game/stop":
            self.handle_game_stop()
            return
        if self.path == "/api/game/save":
            self.handle_game_save()
            return
        if self.path == "/api/game/load":
            self.handle_game_load()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

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

    def handle_saves_list(self) -> None:
        os.makedirs(self.saves_dir, exist_ok=True)
        files = [
            name
            for name in os.listdir(self.saves_dir)
            if name.endswith(".json") and os.path.isfile(os.path.join(self.saves_dir, name))
        ]
        files.sort()
        self.send_json({"saves": files})

    def handle_game_new(self) -> None:
        payload = self.read_json()
        try:
            player_count = int(payload.get("players", 4))
            human_index = int(payload.get("human_index", 0))
        except (TypeError, ValueError) as exc:
            self.send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        bot_types = payload.get("bot_types") or []
        seed = payload.get("seed")
        if not 2 <= player_count <= 6:
            self.send_json_error("players must be between 2 and 6", HTTPStatus.BAD_REQUEST)
            return
        if not 0 <= human_index < player_count:
            self.send_json_error("human_index out of range", HTTPStatus.BAD_REQUEST)
            return
        if bot_types and len(bot_types) != player_count:
            self.send_json_error("bot_types length must match players", HTTPStatus.BAD_REQUEST)
            return
        if not bot_types:
            bot_types = ["random"] * player_count
        bot_types = list(bot_types)
        bot_types[human_index] = "human"
        session = GameSession(
            player_count=player_count,
            human_index=human_index,
            bot_types=bot_types,
            seed=seed,
            record_eval_in_replay=self.session_store.record_eval_in_replay,
        )
        self.session_store.session = session
        events = session.step()
        self.send_json(session.build_response(events, bot_eval=session.consume_bot_eval()))

    def handle_game_action(self) -> None:
        session = self.session_store.session
        if session is None:
            self.send_json_error("No active session", HTTPStatus.BAD_REQUEST)
            return
        payload = self.read_json()
        if payload.get("session_id") != session.session_id:
            self.send_json_error("Session mismatch", HTTPStatus.BAD_REQUEST)
            return
        action = payload.get("action")
        if not isinstance(action, dict):
            self.send_json_error("Missing action", HTTPStatus.BAD_REQUEST)
            return
        try:
            events = session.apply_action(action)
            if not session.pending_decision:
                events.extend(session.step())
            replay_name = session.save_replay(self.replays_dir)
            response = session.build_response(events, bot_eval=session.consume_bot_eval())
            if replay_name:
                response["replay_saved"] = replay_name
            self.send_json(response)
        except ValueError as exc:
            self.send_json_error(str(exc), HTTPStatus.BAD_REQUEST)

    def handle_game_step(self) -> None:
        session = self.session_store.session
        if session is None:
            self.send_json_error("No active session", HTTPStatus.BAD_REQUEST)
            return
        payload = self.read_json()
        if payload.get("session_id") != session.session_id:
            self.send_json_error("Session mismatch", HTTPStatus.BAD_REQUEST)
            return
        try:
            events = session.step()
            replay_name = session.save_replay(self.replays_dir)
            response = session.build_response(events, bot_eval=session.consume_bot_eval())
            if replay_name:
                response["replay_saved"] = replay_name
            self.send_json(response)
        except ValueError as exc:
            self.send_json_error(str(exc), HTTPStatus.BAD_REQUEST)

    def handle_game_pause(self) -> None:
        session = self.session_store.session
        if session is None:
            self.send_json_error("No active session", HTTPStatus.BAD_REQUEST)
            return
        payload = self.read_json()
        if payload.get("session_id") != session.session_id:
            self.send_json_error("Session mismatch", HTTPStatus.BAD_REQUEST)
            return
        session.paused = True
        self.send_json(session.build_response([], bot_eval=session.consume_bot_eval()))

    def handle_game_resume(self) -> None:
        session = self.session_store.session
        if session is None:
            self.send_json_error("No active session", HTTPStatus.BAD_REQUEST)
            return
        payload = self.read_json()
        if payload.get("session_id") != session.session_id:
            self.send_json_error("Session mismatch", HTTPStatus.BAD_REQUEST)
            return
        session.paused = False
        events = session.step()
        self.send_json(session.build_response(events, bot_eval=session.consume_bot_eval()))

    def handle_game_stop(self) -> None:
        payload = self.read_json()
        session = self.session_store.session
        if session is None:
            self.send_json_error("No active session", HTTPStatus.BAD_REQUEST)
            return
        if payload.get("session_id") != session.session_id:
            self.send_json_error("Session mismatch", HTTPStatus.BAD_REQUEST)
            return
        self.session_store.session = None
        self.send_json({"stopped": True})

    def handle_game_save(self) -> None:
        session = self.session_store.session
        if session is None:
            self.send_json_error("No active session", HTTPStatus.BAD_REQUEST)
            return
        payload = self.read_json()
        if payload.get("session_id") != session.session_id:
            self.send_json_error("Session mismatch", HTTPStatus.BAD_REQUEST)
            return
        save_name = payload.get("save_name", "").strip()
        if not save_name:
            self.send_json_error("Save name required", HTTPStatus.BAD_REQUEST)
            return
        if "/" in save_name or "\\" in save_name:
            self.send_json_error("Invalid save name", HTTPStatus.BAD_REQUEST)
            return
        os.makedirs(self.saves_dir, exist_ok=True)
        filename = f"{save_name}.json" if not save_name.endswith(".json") else save_name
        path = os.path.join(self.saves_dir, filename)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(session.to_save_dict(), handle, indent=2, ensure_ascii=False)
        self.send_json({"saved": filename})

    def handle_game_load(self) -> None:
        payload = self.read_json()
        save_name = payload.get("save_name", "").strip()
        if not save_name:
            self.send_json_error("Save name required", HTTPStatus.BAD_REQUEST)
            return
        if "/" in save_name or "\\" in save_name:
            self.send_json_error("Invalid save name", HTTPStatus.BAD_REQUEST)
            return
        filename = f"{save_name}.json" if not save_name.endswith(".json") else save_name
        path = os.path.join(self.saves_dir, filename)
        if not os.path.isfile(path):
            self.send_json_error("Save not found", HTTPStatus.NOT_FOUND)
            return
        with open(path, "r", encoding="utf-8") as handle:
            save_data = json.load(handle)
        session = GameSession.from_save_dict(save_data)
        self.session_store.session = session
        events = session.step()
        self.send_json(session.build_response(events, bot_eval=session.consume_bot_eval()))

    def read_json(self) -> Dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        payload = self.rfile.read(length)
        if not payload:
            return {}
        try:
            return json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def send_json(self, payload: Dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json_error(self, message: str, status: HTTPStatus) -> None:
        data = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay web server")
    parser.add_argument("--replays-dir", type=str, default="replays", help="Replay folder")
    parser.add_argument("--saves-dir", type=str, default="saves", help="Save game folder")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface")
    parser.add_argument(
        "--record-eval-in-replay",
        action="store_true",
        help="Store bot eval data in replay events",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.makedirs(args.replays_dir, exist_ok=True)
    os.makedirs(args.saves_dir, exist_ok=True)
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    session_store = SessionStore(record_eval_in_replay=args.record_eval_in_replay)
    handler = lambda *handler_args, **handler_kwargs: ReplayRequestHandler(  # noqa: E731
        *handler_args,
        replays_dir=args.replays_dir,
        saves_dir=args.saves_dir,
        static_dir=static_dir,
        session_store=session_store,
        **handler_kwargs,
    )
    with TCPServer((args.host, args.port), handler) as httpd:
        print(f"Serving on http://{args.host}:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
