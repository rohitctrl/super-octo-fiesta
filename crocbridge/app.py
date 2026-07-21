"""Flask app: JSON API + the single-page UI."""

import subprocess
import sys
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, request, send_from_directory

from . import crocbin, pairing
from .sender import SendBusy

SETTINGS_KEYS = (
    "device_name", "download_dir", "relay", "relay_pass", "socks5", "overwrite",
    "throttle_upload",
)

# Methods that change state and so must be protected from cross-origin abuse.
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(config, state, receiver, sender):
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    @app.before_request
    def block_cross_origin():
        # The API has no auth because it lives on 127.0.0.1, but a web page the
        # user visits can still POST to it cross-origin (a CSRF). The browser
        # is forced to send an Origin header on such requests and cannot forge
        # the target Host, so: if Origin is present it must match the host the
        # request actually reached. A missing Origin means a non-browser client
        # (curl, the e2e) or a same-origin GET — those are allowed.
        if request.method not in UNSAFE_METHODS:
            return
        origin = request.headers.get("Origin")
        if origin is not None and urlparse(origin).netloc != request.host:
            abort(403)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/status")
    def status():
        s = state.snapshot()
        return jsonify(
            {
                "croc": crocbin.detect(),
                "paired": config.get("paired"),
                "pending_pairing": config.get("pending_pairing") is not None,
                "device_name": config.get("device_name"),
                "peer_name": config.get("peer_name"),
                "download_dir": str(config.download_dir()),
                "receiver": s["receiver"],
                "send": s["send"],
                "history_len": len(s["history"]),
            }
        )

    @app.get("/api/settings")
    def get_settings():
        snap = config.snapshot()
        return jsonify({k: snap[k] for k in SETTINGS_KEYS})

    @app.put("/api/settings")
    def put_settings():
        body = request.get_json(force=True, silent=True) or {}
        updates = {k: body[k] for k in SETTINGS_KEYS if k in body}
        if "device_name" in updates and not str(updates["device_name"]).strip():
            return jsonify({"error": "Device name can't be empty."}), 400
        if updates:
            config.set(**updates)
            receiver.restart()  # pick up new relay/dir/overwrite flags
        return get_settings()

    @app.post("/api/pair/create")
    def pair_create():
        if config.get("paired"):
            return jsonify({"error": "Already linked. Unpair first to start over."}), 409
        body = request.get_json(force=True, silent=True) or {}
        if body.get("device_name"):
            config.set(device_name=str(body["device_name"]).strip())
        if not config.get("device_name"):
            return jsonify({"error": "Name this device first."}), 400
        return jsonify({"pairing_string": pairing.create(config)})

    @app.post("/api/pair/accept")
    def pair_accept():
        if config.get("paired"):
            return jsonify({"error": "Already linked. Unpair first to start over."}), 409
        body = request.get_json(force=True, silent=True) or {}
        name = str(body.get("device_name", "")).strip()
        if not name:
            return jsonify({"error": "Name this device first."}), 400
        try:
            confirmation = pairing.accept(config, str(body.get("pairing_string", "")).strip(), name)
        except pairing.PairingError as exc:
            return jsonify({"error": str(exc)}), 400
        receiver.start()
        return jsonify({"confirmation_string": confirmation, "peer_name": config.get("peer_name")})

    @app.post("/api/pair/confirm")
    def pair_confirm():
        body = request.get_json(force=True, silent=True) or {}
        try:
            peer = pairing.confirm(config, str(body.get("confirmation_string", "")).strip())
        except pairing.PairingError as exc:
            return jsonify({"error": str(exc)}), 400
        receiver.start()
        return jsonify({"peer_name": peer})

    @app.post("/api/unpair")
    def unpair():
        body = request.get_json(force=True, silent=True) or {}
        if body.get("confirm") is not True:
            return jsonify({"error": "Confirmation required."}), 400
        receiver.stop()
        config.wipe_pairing()
        return jsonify({})

    @app.post("/api/send")
    def send():
        if not config.get("paired"):
            return jsonify({"error": "Pair with another device first."}), 400
        files = request.files.getlist("files[]") or request.files.getlist("files")
        if not files:
            return jsonify({"error": "No files in the request."}), 400
        try:
            sender.start_send(files)
        except SendBusy:
            return jsonify({"error": "A transfer is already crossing. Wait for it to finish."}), 409
        except ValueError:
            return jsonify({"error": "No files in the request."}), 400
        return jsonify({"ok": True}), 202

    @app.post("/api/send/cancel")
    def send_cancel():
        sender.cancel()
        return jsonify({})

    @app.get("/api/history")
    def history():
        return jsonify({"transfers": state.snapshot()["history"]})

    @app.post("/api/open-folder")
    def open_folder():
        folder = str(config.download_dir())
        opener = {
            "darwin": ["open"],
            "linux": ["xdg-open"],
        }.get(sys.platform if sys.platform != "win32" else None)
        if sys.platform == "win32":
            import os

            os.startfile(folder)  # noqa: S606 - local desktop action
            return jsonify({"ok": True})
        if opener:
            try:
                subprocess.Popen(
                    opener + [folder],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return jsonify({"ok": True})
            except OSError:
                pass
        return jsonify({"ok": False, "path": folder})

    return app
