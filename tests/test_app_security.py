"""API security guards: cross-origin CSRF protection and re-pair blocking."""

import pytest

from crocbridge.app import create_app
from crocbridge.config import ConfigManager
from crocbridge.state import AppState


class _NoopDaemon:
    def start(self): pass
    def stop(self): pass
    def restart(self): pass


@pytest.fixture
def client(tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    config.set(device_name="alpha")
    app = create_app(config, AppState(), _NoopDaemon(), _NoopDaemon())
    app.testing = True
    return app.test_client(), config


def test_cross_origin_post_rejected(client):
    c, _ = client
    r = c.post("/api/pair/create", json={}, headers={"Origin": "https://evil.com"})
    assert r.status_code == 403


def test_same_origin_post_allowed(client):
    c, _ = client
    r = c.post("/api/pair/create", json={}, headers={"Origin": "http://localhost", "Host": "localhost"})
    assert r.status_code == 200


def test_missing_origin_allowed(client):
    # non-browser clients (curl, the e2e) send no Origin header
    c, _ = client
    r = c.post("/api/pair/create", json={})
    assert r.status_code == 200


def test_cross_origin_blocked_before_side_effects(client):
    # a rejected accept must not pair the device
    c, config = client
    c.post(
        "/api/pair/accept",
        json={"pairing_string": "CB1.whatever", "device_name": "x"},
        headers={"Origin": "https://evil.com"},
    )
    assert config.get("paired") is False
    assert config.get("secret") is None


def test_get_status_allowed_cross_origin_but_reads_only(client):
    # SOP stops a web page from reading the response; the request itself is
    # harmless (read-only), so we don't block safe methods
    c, _ = client
    r = c.get("/api/status", headers={"Origin": "https://evil.com"})
    assert r.status_code == 200


def test_accept_blocked_when_already_paired(client):
    c, config = client
    config.set(paired=True, peer_name="bravo", secret="c2VjcmV0")
    r = c.post("/api/pair/accept", json={"pairing_string": "CB1.x", "device_name": "x"})
    assert r.status_code == 409
    assert config.get("peer_name") == "bravo"  # existing pairing untouched
