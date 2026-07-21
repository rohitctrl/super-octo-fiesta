"""In-memory, thread-safe application state shared by the daemons and the API."""

import threading
import time


class AppState:
    def __init__(self):
        self._lock = threading.Lock()
        self.receiver = {
            "state": "stopped",  # stopped | listening | receiving | error
            "progress": None,
            "error": None,
            "received_files": [],  # [{name, bytes, at}]
        }
        self.send = {
            "state": "idle",  # idle | staging | connecting | sending | done | cancelled | error
            "files": [],
            "progress": None,
            "error": None,
        }
        self.history = []  # [{id, direction, files, total_bytes, started_at, duration_s, result}]
        self._next_id = 1

    def update_receiver(self, **kwargs):
        with self._lock:
            self.receiver.update(kwargs)

    def update_send(self, **kwargs):
        with self._lock:
            self.send.update(kwargs)

    def add_received_files(self, entries):
        with self._lock:
            self.receiver["received_files"] = (entries + self.receiver["received_files"])[:200]

    def add_history(self, direction, files, total_bytes, started_at, result):
        with self._lock:
            entry = {
                "id": self._next_id,
                "direction": direction,
                "files": files,
                "total_bytes": total_bytes,
                "started_at": started_at,
                "duration_s": round(time.time() - started_at, 1),
                "result": result,
            }
            self._next_id += 1
            self.history.insert(0, entry)
            del self.history[200:]
            return entry

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "receiver": {**self.receiver, "received_files": list(self.receiver["received_files"])},
                "send": {**self.send, "files": list(self.send["files"])},
                "history": [dict(h) for h in self.history],
            }
