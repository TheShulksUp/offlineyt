"""The suite must never touch the developer's real config or library."""

import hashlib
import os

import helpers

y = helpers.load_yosync()
REAL_CONFIG = os.path.join(os.path.expanduser("~"), ".config", "yosync",
                           "config.json")


def test_loaded_module_never_points_at_the_real_config():
    assert os.path.abspath(y.CONFIG_PATH) != os.path.abspath(REAL_CONFIG), (
        "tests would overwrite the real config at " + REAL_CONFIG)
    assert y.CONFIG_DIR.startswith("/var/folders") or "yosync-cfg-" in y.CONFIG_DIR


def test_tmp_cfg_library_is_a_throwaway(tmp_path):
    cfg = helpers.tmp_cfg(y)
    assert cfg["dest"] != REAL_CONFIG
    assert "yosync-test-" in cfg["dest"]
    assert os.path.isdir(cfg["dest"])


def test_writing_config_cannot_reach_the_real_file():
    before = None
    if os.path.exists(REAL_CONFIG):
        with open(REAL_CONFIG, "rb") as fh:
            before = hashlib.sha256(fh.read()).hexdigest()
    cfg = helpers.tmp_cfg(y, exclude_channels=["SomeChannel"])
    y.save_config(cfg)
    assert os.path.exists(y.CONFIG_PATH)
    assert os.path.abspath(y.CONFIG_PATH) != os.path.abspath(REAL_CONFIG)
    if before is not None:
        with open(REAL_CONFIG, "rb") as fh:
            after = hashlib.sha256(fh.read()).hexdigest()
        assert after == before, "the real config.json was modified by a test"
