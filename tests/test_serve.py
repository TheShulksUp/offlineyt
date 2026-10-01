"""The settings page must open instantly, even while a sync is running.

Regression: main() used to call acquire_lock() before the --serve branch, and
acquire_lock() takes a *blocking* flock. So with any sync in flight (the 6am
daemon, a --dry-run, a --verify) `yosync --serve` hung, the browser opened to
"connection refused", and the whole page -- Status included -- looked like it
had never been set up. The Status tab was implemented all along.
"""

import json
import os
import sys

import helpers

y = helpers.load_yosync()


def _cfg_on(tmp_path, monkeypatch):
    """Point yosync at a throwaway config + library and return the config."""
    cfg = y.default_config(str(tmp_path))
    cfgp = str(tmp_path / "config.json")
    with open(cfgp, "w") as fh:
        json.dump(cfg, fh)
    monkeypatch.setattr(y, "CONFIG_PATH", cfgp)
    return cfg


def test_serve_does_not_block_on_the_sync_lock(tmp_path, monkeypatch):
    """--serve must serve even though another sync owns the lock.

    acquire_lock() takes a *blocking* flock, so the old ordering (lock, then
    serve) meant the page could not start until the running sync finished.
    Asserting via a raising stub rather than an actually-held lock keeps the
    test fast and deterministic: if --serve ever locks again, this fails
    immediately instead of hanging until the suite timeout.
    """
    _cfg_on(tmp_path, monkeypatch)
    served = []

    def must_not_lock():
        raise AssertionError("--serve must not take the sync lock")

    monkeypatch.setattr(y, "acquire_lock", must_not_lock)
    monkeypatch.setattr(y, "serve_settings",
                        lambda cfg, silent=False: served.append(cfg))
    monkeypatch.setattr(sys, "argv", ["yosync", "--serve"])
    y.main()

    assert len(served) == 1, "the settings page never started"
    assert served[0]["dest"] == str(tmp_path)


def test_serve_does_not_touch_the_library_or_state(tmp_path, monkeypatch):
    """Serving settings is read-only apart from config: it must not walk into
    the sync pipeline (no downloads, no state rewrite) just to show a page."""
    _cfg_on(tmp_path, monkeypatch)
    called = []
    for name in ("enrich_channels", "download", "merge_history", "report",
                 "resolve_ad_videos", "analyze"):
        monkeypatch.setattr(y, name,
                            lambda *a, **k: called.append(name))
    monkeypatch.setattr(y, "serve_settings", lambda cfg, silent=False: None)
    monkeypatch.setattr(sys, "argv", ["yosync", "--serve"])
    y.main()
    assert called == [], "--serve ran sync work: %s" % called


def test_other_runs_still_take_the_sync_lock(tmp_path, monkeypatch):
    """The lock is only skipped for --serve; a real sync must still take it,
    otherwise two syncs could fight over state.json and the library."""
    _cfg_on(tmp_path, monkeypatch)

    acquired = []
    monkeypatch.setattr(y, "acquire_lock", lambda: acquired.append(1) or "lock")
    monkeypatch.setattr(sys, "argv", ["yosync", "--serve"])
    monkeypatch.setattr(y, "serve_settings", lambda cfg, silent=False: None)
    y.main()
    assert acquired == [], "--serve should not lock"

    acquired.clear()
    monkeypatch.setattr(sys, "argv", ["yosync", "--dry-run"])
    for name in ("enrich_channels", "download", "report", "resolve_ad_videos",
                 "rclone_pull", "inbox_download"):
        monkeypatch.setattr(y, name, lambda *a, **k: None)
    y.main()
    assert acquired == [1], "a dry run must still take the sync lock"


def test_status_payload_reports_the_interesting_numbers(tmp_path, monkeypatch):
    """Status is only useful if it carries library/sync/ad state, not just
    last_run."""
    dest = tmp_path / "lib"
    (dest / "Chan").mkdir(parents=True)
    (dest / ".yosync").mkdir()
    (dest / "Chan" / "a [aaaaaaaaaaa].mp4").write_bytes(b"x" * 2048)
    state = {
        "history": [{"id": "aaaaaaaaaaa", "time": "2026-09-25T23:00:00+00:00",
                     "channel": "Chan",
                     "channel_url": "https://www.youtube.com/channel/uc_x"}],
        "index": {"aaaaaaaaaaa": {"channel": "Chan", "name": "Chan",
                                  "path": str(dest / "Chan" / "a [aaaaaaaaaaa].mp4")}},
        "last_run": "2026-09-25T23:00:00+00:00",
        "ad_videos": {"bbbbbbbbbbb": 1},
        "ad_landings": {"adv": "Adv"},
        "ad_purged_channels": [],
    }
    with open(dest / ".yosync" / "state.json", "w") as fh:
        json.dump(state, fh)

    cfg = y.default_config(str(dest))
    cfg["daemon"] = True
    # daemon status comes from the OS, not the config, so pin it here and let
    # the dedicated test below cover the real detection
    monkeypatch.setattr(y, "daemon_installed", lambda: True)
    monkeypatch.setattr(y, "daemon_next_run", lambda: "daily 06:00")
    payload = y._state_payload(cfg)

    assert payload["index"] == 1
    assert payload["channels"] == 1
    # one watch is not "hot" (hot_min_watches defaults to 4), but the channel
    # must still be counted as tracked
    assert payload["hot_count"] == 0
    assert payload["hot"] == []
    assert payload["daemon"] is True
    assert payload["ad_videos"] == 1
    assert payload["ad_channels"] == 1
    assert payload["ad_purged"] == 0
    assert payload["last_run"] == "2026-09-25T23:00:00+00:00"
    # .yosync is metadata, not library, so it must not inflate size_gb
    assert payload["size_gb"] < 0.001


def test_status_payload_survives_unreadable_state(tmp_path):
    """A corrupt/absent state.json must render an empty Status page, not a
    traceback -- channels is computed inside a try, so it needs a default."""
    dest = tmp_path / "lib"
    (dest / ".yosync").mkdir(parents=True)
    with open(dest / ".yosync" / "state.json", "w") as fh:
        fh.write("{not json")
    payload = y._state_payload(y.default_config(str(dest)))
    assert payload["index"] == 0
    assert payload["channels"] == 0
    assert payload["hot"] == []


def test_library_size_ignores_metadata_dir(tmp_path):
    dest = tmp_path / "lib"
    (dest / "C").mkdir(parents=True)
    (dest / ".yosync").mkdir()
    (dest / "C" / "v.mp4").write_bytes(b"a" * 100)
    (dest / ".yosync" / "state.json").write_bytes(b"b" * 5000)
    assert y.library_size(str(dest)) == 100


def test_daemon_status_reads_the_schedule_not_the_config(tmp_path, monkeypatch):
    """Status must report what will actually run at 6am.

    cfg["daemon"] and the installed LaunchAgent can disagree -- e.g. after a
    config restore -- and reporting the stale config flag once made Status say
    "background sync: off" while the agent was very much installed.
    """
    import plistlib

    monkeypatch.setattr(y, "PLIST_PATH", str(tmp_path / "com.vyom.yosync.plist"))
    monkeypatch.setattr(y, "sys", type("S", (), {"platform": "darwin", "executable": "/usr/bin/python3"}))

    cfg = y.default_config(str(tmp_path))
    cfg["daemon"] = False          # stale config flag
    payload = y._state_payload(cfg)
    assert payload["daemon"] is False, "no plist on disk -> must report off"

    with open(tmp_path / "com.vyom.yosync.plist", "wb") as fh:
        plistlib.dump({"Label": "com.vyom.yosync",
                       "StartCalendarInterval": {"Hour": 6, "Minute": 0}}, fh)
    assert y.daemon_installed() is True
    assert y.daemon_next_run() == "daily 06:00"

    payload = y._state_payload(cfg)
    assert payload["daemon"] is True, "installed agent must win over cfg"
    assert payload["daemon_next"] == "daily 06:00"


def test_daemon_status_handles_a_corrupt_plist(tmp_path, monkeypatch):
    monkeypatch.setattr(y, "PLIST_PATH", str(tmp_path / "broken.plist"))
    monkeypatch.setattr(y, "sys", type("S", (), {"platform": "darwin", "executable": "/usr/bin/python3"}))
    with open(tmp_path / "broken.plist", "wb") as fh:
        fh.write(b"not a plist at all")
    assert y.daemon_installed() is False
    assert y.daemon_next_run() is None


# --- configurable daemon time ---------------------------------------------------

def test_parse_daemon_time_accepts_valid_forms():
    assert y.parse_daemon_time("06:00") == (6, 0)
    assert y.parse_daemon_time("6:00") == (6, 0)
    assert y.parse_daemon_time("23:30") == (23, 30)
    assert y.parse_daemon_time("00:15") == (0, 15)
    assert y.parse_daemon_time(" 07:05 ") == (7, 5)


def test_parse_daemon_time_rejects_garbage():
    for bad in ("", "6", "6am", "24:00", "12:60", "12:30:00", "noon",
                None, 600, "12-30", "-1:00"):
        assert y.parse_daemon_time(bad) is None, bad


def test_daemon_time_str_falls_back_to_default():
    assert y.daemon_time_str({}) == "06:00"
    assert y.daemon_time_str({"daemon_time": "23:30"}) == "23:30"
    assert y.daemon_time_str({"daemon_time": "nonsense"}) == "06:00"
    assert y.daemon_time_str({"daemon_time": "24:00"}) == "06:00"


def test_default_config_has_daemon_time():
    cfg = y.default_config("/tmp/whatever")
    assert cfg["daemon_time"] == "06:00"


def test_schema_exposes_daemon_time():
    keys = [f["key"] for g in y.SETTINGS_SCHEMA for f in g["fields"]]
    assert "daemon_time" in keys


def test_write_daemon_uses_configured_time(tmp_path, monkeypatch):
    """The plist must carry the configured hour/minute, not a hardcoded 6am."""
    import plistlib

    plist_path = tmp_path / "com.vyom.yosync.plist"
    monkeypatch.setattr(y, "PLIST_PATH", str(plist_path))
    monkeypatch.setattr(y, "sys", type("S", (), {"platform": "darwin", "executable": "/usr/bin/python3"}))
    monkeypatch.setattr(y, "_load_daemon", lambda silent: None)
    monkeypatch.setattr(y, "_unload_daemon", lambda silent: None)

    cfg = y.default_config(str(tmp_path))
    cfg["daemon_time"] = "23:30"
    y.write_daemon(True, cfg, silent=True)

    with open(plist_path, "rb") as fh:
        when = plistlib.load(fh)["StartCalendarInterval"]
    assert when == {"Hour": 23, "Minute": 30}, when


def test_write_daemon_falls_back_for_bad_time(tmp_path, monkeypatch):
    import plistlib

    plist_path = tmp_path / "com.vyom.yosync.plist"
    monkeypatch.setattr(y, "PLIST_PATH", str(plist_path))
    monkeypatch.setattr(y, "sys", type("S", (), {"platform": "darwin", "executable": "/usr/bin/python3"}))
    monkeypatch.setattr(y, "_load_daemon", lambda silent: None)

    cfg = y.default_config(str(tmp_path))
    cfg["daemon_time"] = "99:99"
    y.write_daemon(True, cfg, silent=True)

    with open(plist_path, "rb") as fh:
        when = plistlib.load(fh)["StartCalendarInterval"]
    assert when == {"Hour": 6, "Minute": 0}, when


def test_linux_timer_uses_configured_time(tmp_path, monkeypatch):
    monkeypatch.setattr(y, "HOME", str(tmp_path))
    monkeypatch.setattr(y, "sys", type("S", (), {"platform": "linux", "executable": "/usr/bin/python3"}))
    monkeypatch.setattr(y, "_systemctl_user", lambda *a: type("R", (), {"returncode": 0})())

    cfg = y.default_config(str(tmp_path))
    cfg["daemon_time"] = "01:45"
    y.write_daemon(True, cfg, silent=True)

    timer = (tmp_path / ".config" / "systemd" / "user" / "yosync.timer").read_text()
    assert "OnCalendar=*-*-* 01:45:00" in timer, timer
    assert "daily at 01:45" in timer, timer


def test_settings_page_rejects_a_bad_daemon_time():
    cfg = y.default_config("/tmp/whatever")
    merged, errors = y._apply_config_update(cfg, {"daemon_time": "25:00"})
    assert any("daemon time" in e for e in errors), errors
    assert merged["daemon_time"] == "06:00", "bad value must not be stored"


def test_settings_page_accepts_a_good_daemon_time():
    cfg = y.default_config("/tmp/whatever")
    merged, errors = y._apply_config_update(cfg, {"daemon_time": "22:15"})
    assert errors == [], errors
    assert merged["daemon_time"] == "22:15"


def test_load_config_fills_in_new_settings(tmp_path, monkeypatch):
    """A config written before a setting existed must still get the default,
    otherwise the setting is silently absent until the next save."""
    cfgp = tmp_path / "config.json"
    with open(cfgp, "w") as fh:
        json.dump({"dest": str(tmp_path), "daemon": True}, fh)
    monkeypatch.setattr(y, "CONFIG_PATH", str(cfgp))
    cfg = y.load_config(silent=True)
    assert cfg["daemon_time"] == "06:00", cfg.get("daemon_time")
    assert cfg["daemon"] is True, "existing values must be preserved"
