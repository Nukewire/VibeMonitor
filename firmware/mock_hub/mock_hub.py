"""Mock VibeMonitor hub for firmware development. Serves a canned /state fixture and
accepts /ack (which flips the chosen fixture's waiting flags off in memory).
Usage: python mock_hub.py [fixture_name] [--port 5151] [--token change-me-to-a-random-secret]
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
from flask import Flask, jsonify, request

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def create_app(state: dict, token: str) -> Flask:
    app = Flask(__name__)
    app.config["STATE"] = copy.deepcopy(state)

    def ok_token() -> bool:
        return request.headers.get("X-VibeMonitor-Token") == token

    @app.get("/state")
    def get_state():
        if not ok_token():
            return jsonify({"error": "unauthorized"}), 401
        return jsonify(app.config["STATE"])

    @app.post("/ack")
    def ack():
        if not ok_token():
            return jsonify({"error": "unauthorized"}), 401
        sid = (request.get_json(silent=True) or {}).get("id")
        for s in app.config["STATE"]["sessions"]:
            if s["id"] == sid:
                s["waiting"] = False
                if s["status"] == "waiting":
                    s["status"] = "working"
        return jsonify({"ok": True})

    return app


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture", nargs="?", default="one_waiting")
    ap.add_argument("--port", type=int, default=5151)
    ap.add_argument("--token", default="change-me-to-a-random-secret")
    args = ap.parse_args()
    app = create_app(load(args.fixture), args.token)
    print(f"mock hub: fixture={args.fixture} on http://0.0.0.0:{args.port}")
    app.run(host="0.0.0.0", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
