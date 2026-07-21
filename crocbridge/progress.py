"""Tolerant parsing of croc's stderr progress output.

croc redraws its progress bar with carriage returns, so the reader splits
the raw byte stream on both \r and \n instead of readline(). Each regex
matches independently; a line that matches nothing is kept in a short raw
tail for diagnostics and never raises.
"""

import re
import threading

PCT_RE = re.compile(r"(?P<pct>\d{1,3})%\s*\|")
SIZE_RE = re.compile(
    r"\((?P<done>[\d.]+)\s*(?P<du>[kKMGT]?i?B)?\s*/\s*(?P<total>[\d.]+)\s*(?P<tu>[kKMGT]?i?B)"
)
SPEED_RE = re.compile(r"(?P<speed>[\d.]+)\s*(?P<su>[kKMGT]?i?B)/s")
ETA_RE = re.compile(r"\[(?P<elapsed>[\dhms]+):(?P<eta>[\dhms]+)\]")
FILE_RE = re.compile(r"(?:Sending|Receiving)\s+'(?P<name>[^']+)'")

ERROR_PATTERNS = [
    (re.compile(r"could not connect to.*relay|connection refused|no such host", re.I),
     "Can't reach the relay."),
    (re.compile(r"bad password|wrong password|not authorized", re.I),
     "Relay password rejected."),
    (re.compile(r"permission denied", re.I),
     "Can't write to the download folder."),
]

# croc uses decimal (SI) units in its bars
_UNIT = {"B": 1, "kB": 1000, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4,
         "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}


def _to_bytes(value: str, unit: str | None) -> int | None:
    try:
        return int(float(value) * _UNIT.get(unit or "B", 1))
    except (ValueError, OverflowError):
        return None


def read_stream(fp, on_line):
    """Feed each \r- or \n-terminated chunk of a binary stream to on_line(str)."""
    buf = b""
    while True:
        chunk = fp.read(256)
        if not chunk:
            break
        buf += chunk
        *lines, buf = re.split(rb"[\r\n]", buf)
        for ln in lines:
            if ln.strip():
                on_line(ln.decode("utf-8", "replace"))
    if buf.strip():
        on_line(buf.decode("utf-8", "replace"))


class ProgressParser:
    def __init__(self):
        self._lock = threading.Lock()
        self._reset()

    def _reset(self):
        self.pct = None
        self.speed = None
        self.eta = None
        self.file = None
        self.done_bytes = None
        self.total_bytes = None
        self.error = None
        self.raw_tail = []
        self.saw_progress = False

    def feed(self, line: str):
        with self._lock:
            matched = False
            if m := PCT_RE.search(line):
                pct = int(m.group("pct"))
                if pct <= 100:
                    self.pct = pct
                    self.saw_progress = True
                    matched = True
            if m := SIZE_RE.search(line):
                self.done_bytes = _to_bytes(m.group("done"), m.group("du") or m.group("tu"))
                self.total_bytes = _to_bytes(m.group("total"), m.group("tu"))
                matched = True
            if m := SPEED_RE.search(line):
                self.speed = f"{m.group('speed')} {m.group('su')}/s"
                matched = True
            if m := ETA_RE.search(line):
                self.eta = m.group("eta")
                matched = True
            if m := FILE_RE.search(line):
                self.file = m.group("name")
                matched = True
            for pattern, message in ERROR_PATTERNS:
                if pattern.search(line):
                    self.error = message
                    matched = True
                    break
            if not matched:
                self.raw_tail.append(line)
                del self.raw_tail[:-50]

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "pct": self.pct,
                "speed": self.speed,
                "eta": self.eta,
                "file": self.file,
                "done_bytes": self.done_bytes,
                "total_bytes": self.total_bytes,
                "error": self.error,
                "saw_progress": self.saw_progress,
                "raw_tail": list(self.raw_tail),
            }
