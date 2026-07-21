"""Pairing and confirmation strings.

Pairing string (A -> B):  "CB1." + b64url({"v": 1, "s": b64(secret), "n": A_name})
Confirmation (B -> A):    "CBOK." + b64url({"n": B_name, "m": mac})
where mac = hmac_sha256(secret, "confirm:" + B_name)[:12]. The MAC lets A
accept B's name only from someone actually holding the shared secret.
"""

import base64
import hashlib
import hmac
import json
import secrets as _secrets

PAIR_PREFIX = "CB1."
CONFIRM_PREFIX = "CBOK."


class PairingError(Exception):
    """User-facing pairing failure; str(exc) is safe to show in the UI."""


def _b64e(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode()


def _b64d(blob: str) -> dict:
    try:
        decoded = json.loads(base64.urlsafe_b64decode(blob.encode()))
    except Exception:
        raise PairingError("That doesn't look like a valid string. Copy it again from the other device.")
    if not isinstance(decoded, dict):
        raise PairingError("That doesn't look like a valid string. Copy it again from the other device.")
    return decoded


def _confirm_mac(secret: bytes, name: str) -> str:
    return hmac.new(secret, b"confirm:" + name.encode(), hashlib.sha256).hexdigest()[:12]


def create(config) -> str:
    """Side A: generate a fresh secret, hold it as pending, return the pairing string."""
    secret = _secrets.token_bytes(32)
    config.set(pending_pairing={"secret": base64.b64encode(secret).decode()})
    return PAIR_PREFIX + _b64e({"v": 1, "s": base64.b64encode(secret).decode(), "n": config.get("device_name")})


def accept(config, pairing_string: str, device_name: str) -> str:
    """Side B: adopt the pairing, become fully paired, return the confirmation string."""
    if not pairing_string.startswith(PAIR_PREFIX):
        raise PairingError("That doesn't look like a pairing string. It starts with CB1.")
    payload = _b64d(pairing_string[len(PAIR_PREFIX):])
    if payload.get("v") != 1:
        raise PairingError("This pairing string is from a different CrocBridge version.")
    if not payload.get("s") or not payload.get("n"):
        raise PairingError("This pairing string is incomplete. Copy it again from the other device.")
    try:
        secret = base64.b64decode(payload["s"])
    except Exception:
        raise PairingError("This pairing string is damaged. Copy it again from the other device.")
    if len(secret) != 32:
        raise PairingError("This pairing string is damaged. Copy it again from the other device.")
    config.set(
        device_name=device_name,
        secret=base64.b64encode(secret).decode(),
        peer_name=payload["n"],
        paired=True,
        pending_pairing=None,
    )
    return CONFIRM_PREFIX + _b64e({"n": device_name, "m": _confirm_mac(secret, device_name)})


def confirm(config, confirmation_string: str) -> str:
    """Side A: verify the confirmation, learn B's name, finish pairing. Returns peer name."""
    pending = config.get("pending_pairing")
    if not pending or not pending.get("secret"):
        raise PairingError("No pairing is waiting for confirmation. Start a new pairing first.")
    if not confirmation_string.startswith(CONFIRM_PREFIX):
        raise PairingError("That doesn't look like a confirmation. It starts with CBOK.")
    payload = _b64d(confirmation_string[len(CONFIRM_PREFIX):])
    name, mac = payload.get("n"), payload.get("m")
    if not name or not mac:
        raise PairingError("This confirmation is incomplete. Copy it again from the other device.")
    secret = base64.b64decode(pending["secret"])
    if not hmac.compare_digest(_confirm_mac(secret, name), str(mac)):
        raise PairingError("That confirmation doesn't match this pairing. Check you copied it from the other device.")
    config.set(
        secret=pending["secret"],
        peer_name=name,
        paired=True,
        pending_pairing=None,
    )
    return name
