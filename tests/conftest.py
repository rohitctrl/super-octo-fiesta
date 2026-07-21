import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crocbridge.config import ConfigManager  # noqa: E402


@pytest.fixture
def config_path(tmp_path):
    return tmp_path / "cfg" / "config.json"


@pytest.fixture
def config(config_path):
    return ConfigManager(config_path)
