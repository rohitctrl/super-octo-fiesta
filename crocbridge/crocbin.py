"""Locating croc and building its command lines.

The transfer code is only ever passed via the CROC_SECRET environment
variable (CVE-2023-43621: a code on argv is visible to every local
process). MIN_VERSION gates on releases that support CROC_SECRET.
"""

import os
import re
import shutil
import subprocess

MIN_VERSION = (9, 6, 5)

_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def which_croc() -> str | None:
    return shutil.which("croc")


def croc_version(path: str) -> tuple[int, int, int] | None:
    try:
        out = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = _VERSION_RE.search(out or "")
    return tuple(int(g) for g in m.groups()) if m else None


def detect() -> dict:
    path = which_croc()
    if not path:
        return {"installed": False, "version": None, "supported": False}
    version = croc_version(path)
    supported = version is not None and version >= MIN_VERSION
    return {
        "installed": True,
        "version": ".".join(map(str, version)) if version else None,
        "supported": supported,
    }


def common_flags(config) -> list[str]:
    # relay password travels via CROC_PASS in spawn(), never argv
    flags = []
    if config.get("relay"):
        flags += ["--relay", config.get("relay")]
    if config.get("socks5"):
        flags += ["--socks5", config.get("socks5")]
    return flags


def receive_cmd(config) -> list[str]:
    cmd = ["croc"] + common_flags(config) + ["--yes"]
    if config.get("overwrite"):
        cmd.append("--overwrite")
    cmd += ["--out", str(config.download_dir())]
    return cmd


def send_cmd(config, paths) -> list[str]:
    # --no-local keeps the transfer on the relay: deterministic, and on a
    # shared machine it stops LAN discovery from cross-talking instances.
    cmd = ["croc"] + common_flags(config)
    if config.get("throttle_upload"):  # global flag: must precede the subcommand
        cmd += ["--throttleUpload", str(config.get("throttle_upload"))]
    return cmd + ["send", "--no-local"] + [str(p) for p in paths]


def spawn(cmd: list[str], code: str, relay_pass: str | None = None) -> subprocess.Popen:
    """Start croc with the derived code in its environment, in its own
    process group so shutdown can kill croc and any children together."""
    env = {**os.environ, "CROC_SECRET": code}
    if relay_pass:
        env["CROC_PASS"] = relay_pass
    return subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
