"""Shared test helpers for the OfflineYT / yosync test suite."""

import importlib.machinery
import importlib.util
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YOSYNC = os.path.join(ROOT, "bin", "yosync")


def load_yosync():
    """Import bin/yosync (extensionless) as a module without running main().

    CONFIG_PATH is redirected to a throwaway directory. A test only has to
    override cfg["dest"] to get an isolated library, and anything that writes
    config (the setup wizard, the settings page, main()) lands in the temp
    file -- never in the developer's real ~/.config/yosync/config.json.
    """
    loader = importlib.machinery.SourceFileLoader("yosync", YOSYNC)
    spec = importlib.util.spec_from_loader("yosync", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    mod.CONFIG_DIR = tempfile.mkdtemp(prefix="yosync-cfg-")
    mod.CONFIG_PATH = os.path.join(mod.CONFIG_DIR, "config.json")
    return mod


def tmp_cfg(y, **overrides):
    """A config pointing at a throwaway library folder."""
    dest = tempfile.mkdtemp(prefix="yosync-test-")
    cfg = y.default_config(dest)
    cfg.update(overrides)
    return cfg
