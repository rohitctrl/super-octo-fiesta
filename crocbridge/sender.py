"""Send manager: stage uploaded files, run croc send toward the peer's code."""

import base64
import logging
import pathlib
import shutil
import tempfile
import threading
import time

from . import crocbin
from .derivation import derive_code
from .progress import ProgressParser, read_stream
from .receiver import kill_group

log = logging.getLogger("crocbridge.sender")


class SendBusy(Exception):
    pass


class SendManager:
    def __init__(self, config, state):
        self.config = config
        self.state = state
        self._lock = threading.Lock()
        self._proc = None
        self._active = False

    def start_send(self, uploads):
        """uploads: iterable of werkzeug FileStorage. Returns immediately."""
        with self._lock:
            if self._active:
                raise SendBusy()
            self._active = True
        try:
            self.state.update_send(state="staging", files=[], progress=None, error=None)
            stage = pathlib.Path(tempfile.mkdtemp(prefix="crocbridge-send-"))
            names = []
            for f in uploads:
                name = pathlib.PurePosixPath(f.filename or "file").name or "file"
                f.save(stage / name)
                names.append(name)
            if not names:
                raise ValueError("no files")
            self.state.update_send(files=names, state="connecting")
            threading.Thread(
                target=self._run, args=(stage, names), name="sender", daemon=True
            ).start()
        except Exception:
            with self._lock:
                self._active = False
            self.state.update_send(state="error", error="Couldn't prepare the files to send.")
            raise

    # croc pairs correctly only when the sender enters the relay room first.
    # Against an already-listening receiver daemon, attempt 1 fails the
    # handshake — which also knocks that stale receiver out — and the retry
    # then enters the room first and succeeds (the daemon rejoins ~2s later).
    MAX_ATTEMPTS = 4
    RETRY_DELAY_S = 0.4

    def _run(self, stage, names):
        secret = base64.b64decode(self.config.get("secret"))
        code = derive_code(secret, self.config.get("peer_name"))
        started_at = time.time()
        timeout_s = self.config.get("send_timeout_s") or 120
        total_bytes = sum((stage / n).stat().st_size for n in names)

        proc = parser = reader = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            parser = ProgressParser()
            try:
                proc = crocbin.spawn(
                    crocbin.send_cmd(self.config, [stage / n for n in names]), code,
                    relay_pass=self.config.get("relay_pass"),
                )
            except OSError as exc:
                self.state.update_send(state="error", error=f"Couldn't start croc: {exc}")
                self._cleanup(stage)
                return
            with self._lock:
                self._proc = proc

            reader = threading.Thread(target=read_stream, args=(proc.stderr, parser.feed), daemon=True)
            reader.start()

            timed_out = False
            while proc.poll() is None:
                snap = parser.snapshot()
                if snap["saw_progress"]:
                    self.state.update_send(state="sending", progress=snap)
                elif time.time() - started_at > timeout_s:
                    timed_out = True
                    kill_group(proc)
                    break
                time.sleep(0.25)

            proc.wait()
            reader.join(timeout=5)
            snap = parser.snapshot()

            if timed_out:
                with self._lock:
                    self._proc = None
                self.state.update_send(
                    state="error",
                    error="No one picked up on the other bank. Is the other device running and online?",
                    progress=None,
                )
                self.state.add_history("out", names, total_bytes, started_at, "timeout")
                self._cleanup(stage)
                return

            cancelled = self.state.snapshot()["send"]["state"] == "cancelled"
            handshake_failed = proc.returncode != 0 and not snap["saw_progress"]
            if handshake_failed and not cancelled and attempt < self.MAX_ATTEMPTS:
                time.sleep(self.RETRY_DELAY_S)
                continue
            break

        with self._lock:
            self._proc = None

        if self.state.snapshot()["send"]["state"] == "cancelled":
            result = "cancelled"
        elif proc.returncode == 0:
            self.state.update_send(state="done", progress=snap)
            result = "ok"
        else:
            self.state.update_send(
                state="error",
                error=snap["error"] or "The transfer failed. Try sending again.",
            )
            result = "error"
        self.state.add_history("out", names, total_bytes, started_at, result)
        log.info("send finished: %s (%s)", result, ", ".join(names))
        self._cleanup(stage)

    def cancel(self):
        with self._lock:
            proc = self._proc
        if proc:
            self.state.update_send(state="cancelled", progress=None)
            kill_group(proc)

    def stop(self):
        with self._lock:
            proc = self._proc
        if proc:
            kill_group(proc)

    def _cleanup(self, stage):
        shutil.rmtree(stage, ignore_errors=True)
        with self._lock:
            self._active = False
