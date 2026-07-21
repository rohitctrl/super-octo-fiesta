"""Persistent per-device configuration: ~/.crocbridge/config.json by default.

Only JSON on disk plus in-memory state — no database. Writes are atomic
(tmp file + os.replace) so a crash never leaves a half-written config.
"""

import json
import os
import threading
import time
from pathlib import Path

DEFAULTS = {
    "device_name": "",
    "secret": None,  # base64 of 32 random bytes, shared with the peer
    "peer_name": None,
    "paired": False,
    "pending_pairing": None,  # side A holds {"secret": ...} until confirmation
    "download_dir": str(Path.home() / "CrocBridge"),
    "relay": None,
    "relay_pass": None,
    "socks5": None,
    "overwrite": True,
    "send_timeout_s": 120,
    "throttle_upload": None,  # e.g. "10M" -> croc --throttleUpload (advanced)
}

PAIRING_KEYS = ("secret", "peer_name", "paired", "pending_pairing")


class ConfigManager:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.recovered_from_corruption = False
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            backup = self.path.with_name(self.path.name + f".corrupt-{int(time.time())}")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self.recovered_from_corruption = True
            return
        for key in DEFAULTS:
            if key in raw:
                self._data[key] = raw[key]

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

    def get(self, key):
        with self._lock:
            return self._data[key]

    def set(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                if key not in DEFAULTS:
                    raise KeyError(key)
                self._data[key] = value
        self.save()

    def wipe_pairing(self):
        """Unpair: forget the secret and peer, keep device settings."""
        self.set(**{k: DEFAULTS[k] for k in PAIRING_KEYS})

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)

    def download_dir(self) -> Path:
        return Path(self.get("download_dir")).expanduser()
