import json

from crocbridge.config import ConfigManager


def test_defaults_created_on_missing_file(config, config_path):
    assert config.get("paired") is False
    assert config.get("secret") is None
    assert config.get("overwrite") is True
    assert config.get("send_timeout_s") == 120
    assert config.get("download_dir")  # non-empty default


def test_save_load_round_trip(config, config_path):
    config.set(device_name="study-mac", relay="127.0.0.1:9021", overwrite=False)
    reloaded = ConfigManager(config_path)
    assert reloaded.get("device_name") == "study-mac"
    assert reloaded.get("relay") == "127.0.0.1:9021"
    assert reloaded.get("overwrite") is False


def test_save_is_atomic_no_tmp_left_behind(config, config_path):
    config.set(device_name="x")
    assert config_path.exists()
    leftovers = [p for p in config_path.parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_config_path_override_honored(tmp_path):
    p = tmp_path / "elsewhere" / "custom.json"
    cm = ConfigManager(p)
    cm.set(device_name="bravo")
    assert p.exists()
    assert json.loads(p.read_text())["device_name"] == "bravo"


def test_wipe_pairing_keeps_settings(config):
    config.set(
        device_name="study-mac",
        secret="c2VjcmV0",
        peer_name="kitchen-pc",
        paired=True,
        pending_pairing={"secret": "x"},
        relay="127.0.0.1:9021",
    )
    config.wipe_pairing()
    assert config.get("secret") is None
    assert config.get("peer_name") is None
    assert config.get("paired") is False
    assert config.get("pending_pairing") is None
    # settings survive
    assert config.get("device_name") == "study-mac"
    assert config.get("relay") == "127.0.0.1:9021"


def test_corrupted_json_recovers(config_path):
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{not json!!")
    cm = ConfigManager(config_path)
    assert cm.get("paired") is False
    assert cm.recovered_from_corruption is True
    backups = list(config_path.parent.glob("*.corrupt*"))
    assert backups


def test_unknown_keys_ignored_on_load(config_path):
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"device_name": "a", "bogus_key": 1}))
    cm = ConfigManager(config_path)
    assert cm.get("device_name") == "a"
