import base64
import json

import pytest

from crocbridge import pairing
from crocbridge.config import ConfigManager


@pytest.fixture
def two_configs(tmp_path):
    a = ConfigManager(tmp_path / "a" / "config.json")
    b = ConfigManager(tmp_path / "b" / "config.json")
    a.set(device_name="alpha")
    b.set(device_name="bravo")
    return a, b


def test_full_round_trip(two_configs):
    a, b = two_configs
    pairing_string = pairing.create(a)
    assert pairing_string.startswith("CB1.")
    assert a.get("paired") is False  # A waits for confirmation

    confirmation = pairing.accept(b, pairing_string, device_name="bravo")
    assert confirmation.startswith("CBOK.")
    assert b.get("paired") is True
    assert b.get("peer_name") == "alpha"

    peer = pairing.confirm(a, confirmation)
    assert peer == "bravo"
    assert a.get("paired") is True
    assert a.get("peer_name") == "bravo"
    assert a.get("secret") == b.get("secret")
    assert a.get("pending_pairing") is None


def test_tampered_confirmation_rejected(two_configs):
    a, b = two_configs
    ps = pairing.create(a)
    conf = pairing.accept(b, ps, device_name="bravo")
    payload = json.loads(base64.urlsafe_b64decode(conf[len("CBOK."):]))
    payload["n"] = "mallory"  # rename without recomputing the MAC
    forged = "CBOK." + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(pairing.PairingError):
        pairing.confirm(a, forged)
    assert a.get("paired") is False


def test_confirmation_against_wrong_secret_rejected(tmp_path, two_configs):
    a, b = two_configs
    pairing.accept(b, pairing.create(a), device_name="bravo")
    # a second device that started its own, different pairing
    c = ConfigManager(tmp_path / "c" / "config.json")
    c.set(device_name="charlie")
    other_ps = pairing.create(c)
    d = ConfigManager(tmp_path / "d" / "config.json")
    conf_for_c = pairing.accept(d, other_ps, device_name="delta")
    with pytest.raises(pairing.PairingError):
        pairing.confirm(a, conf_for_c)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "garbage",
        "CB1.not-base64!!",
        "CB1." + base64.urlsafe_b64encode(b"not json").decode(),
        "CB1." + base64.urlsafe_b64encode(json.dumps({"v": 99, "s": "", "n": "x"}).encode()).decode(),
        "CB1." + base64.urlsafe_b64encode(json.dumps({"v": 1}).encode()).decode(),
    ],
)
def test_malformed_pairing_strings_rejected_cleanly(two_configs, bad):
    _, b = two_configs
    with pytest.raises(pairing.PairingError):
        pairing.accept(b, bad, device_name="bravo")
    assert b.get("paired") is False


def test_create_without_confirm_not_paired_but_pending(two_configs):
    a, _ = two_configs
    pairing.create(a)
    assert a.get("paired") is False
    assert a.get("pending_pairing") is not None


def test_confirm_without_pending_rejected(two_configs):
    a, b = two_configs
    conf = pairing.accept(b, pairing.create(a), device_name="bravo")
    pairing.confirm(a, conf)
    with pytest.raises(pairing.PairingError):
        pairing.confirm(a, conf)  # pending is cleared; replay fails
