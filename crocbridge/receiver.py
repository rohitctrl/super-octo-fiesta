"""Receiver daemon: keep a croc listener alive on this device's own code.

The listen loop derives the code fresh on every restart, and a 1-second
tick both watches the child and rotates the listener when the UTC date
changes — but only while idle, never during an active receive.
"""

import base64
import logging
import os
import signal
import subprocess
import threading
import time

from . import crocbin
from .derivation import derive_code
from .progress import ProgressParser, read_stream

log = logging.getLogger("crocbridge.receiver")

RESTART_DELAY_S = 2
HOT_LOOP_WINDOW_S = 60
HOT_LOOP_LIMIT = 5


def kill_group(proc: subprocess.Popen, grace_s: float = 5):
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
            proc.wait(timeout=5)
    except (ProcessLookupError, PermissionError, OSError):
        pass


class ReceiverDaemon:
    def __init__(self, config, state):
        self.config = config
        self.state = state
        self._stop = threading.Event()
        self._proc = None
        self._proc_lock = threading.Lock()
        self._thread = None
        self._recent_exits = []

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="receiver", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        with self._proc_lock:
            if self._proc:
                kill_group(self._proc)
        if self._thread:
            self._thread.join(timeout=10)
        self.state.update_receiver(state="stopped", progress=None)

    def restart(self):
        """Apply changed settings: kill the listener; the loop respawns it."""
        with self._proc_lock:
            if self._proc:
                kill_group(self._proc)

    def _snapshot_dir(self, root):
        try:
            return {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
        except OSError:
            return {}

    def _loop(self):
        while not self._stop.is_set():
            secret_b64 = self.config.get("secret")
            own_name = self.config.get("device_name")
            if not (self.config.get("paired") and secret_b64 and own_name):
                self.state.update_receiver(state="stopped")
                self._stop.wait(1)
                continue

            download_dir = self.config.download_dir()
            try:
                download_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self.state.update_receiver(
                    state="error", error=f"Can't use the download folder: {exc}"
                )
                self._stop.wait(5)
                continue

            secret = base64.b64decode(secret_b64)
            code = derive_code(secret, own_name)
            before = self._snapshot_dir(download_dir)
            parser = ProgressParser()
            started_at = time.time()

            try:
                proc = crocbin.spawn(
                    crocbin.receive_cmd(self.config), code,
                    relay_pass=self.config.get("relay_pass"),
                )
            except OSError as exc:
                self.state.update_receiver(state="error", error=f"Couldn't start croc: {exc}")
                self._stop.wait(RESTART_DELAY_S)
                continue

            with self._proc_lock:
                self._proc = proc
            self.state.update_receiver(state="listening", error=None, progress=None)

            reader = threading.Thread(
                target=read_stream, args=(proc.stderr, parser.feed), daemon=True
            )
            reader.start()

            # Watch the child; rotate at UTC midnight only while idle.
            while proc.poll() is None and not self._stop.is_set():
                snap = parser.snapshot()
                if snap["saw_progress"]:
                    self.state.update_receiver(state="receiving", progress=snap)
                if (
                    derive_code(secret, own_name) != code
                    and not snap["saw_progress"]
                ):
                    log.info("daily code rotated; restarting listener")
                    kill_group(proc)
                    break
                time.sleep(1)

            if self._stop.is_set():
                kill_group(proc)
            proc.wait()
            reader.join(timeout=5)
            with self._proc_lock:
                self._proc = None

            self._finish_run(proc, parser, before, download_dir, started_at)
            if not self._stop.is_set():
                self._watch_hot_loop(started_at)
                self._stop.wait(RESTART_DELAY_S)

    def _finish_run(self, proc, parser, before, download_dir, started_at):
        after = self._snapshot_dir(download_dir)
        new_files = [
            p for p, mtime in after.items() if before.get(p) != mtime
        ]
        snap = parser.snapshot()
        if new_files:
            entries = [
                {
                    "name": str(p.relative_to(download_dir)),
                    "bytes": p.stat().st_size if p.exists() else 0,
                    "at": time.time(),
                }
                for p in sorted(new_files)
            ]
            self.state.add_received_files(entries)
            self.state.add_history(
                direction="in",
                files=[e["name"] for e in entries],
                total_bytes=sum(e["bytes"] for e in entries),
                started_at=started_at,
                result="ok" if proc.returncode == 0 else "error",
            )
            log.info("received %d file(s)", len(new_files))
        elif snap["saw_progress"] or (proc.returncode not in (0, None) and snap["error"]):
            # a transfer was attempted but nothing landed
            self.state.add_history(
                direction="in",
                files=[snap["file"]] if snap["file"] else [],
                total_bytes=snap["total_bytes"] or 0,
                started_at=started_at,
                result="error",
            )
        if snap["error"]:
            self.state.update_receiver(state="error", error=snap["error"], progress=None)
        else:
            self.state.update_receiver(progress=None)

    def _watch_hot_loop(self, started_at):
        now = time.time()
        if now - started_at < 3:
            self._recent_exits.append(now)
        self._recent_exits = [t for t in self._recent_exits if now - t < HOT_LOOP_WINDOW_S]
        if len(self._recent_exits) >= HOT_LOOP_LIMIT:
            self.state.update_receiver(
                state="error",
                error="The receiver keeps stopping right away. Check the relay settings and the raw log.",
            )
            self._stop.wait(30)
            self._recent_exits.clear()
