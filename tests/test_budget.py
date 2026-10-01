"""Budget math, overrides, and channel analysis."""

import datetime

import helpers

y = helpers.load_yosync()


def make_channel(name, distinct_ids, key=None, url=None):
    now = y.now_utc()
    ch = {"key": key or ("k_" + name.lower()), "name": name, "url": url,
          "watches": []}
    for i, vid in enumerate(distinct_ids):
        t = (now - datetime.timedelta(hours=i + 1)).isoformat()
        ch["watches"].append({"id": vid, "time": t, "title": vid,
                              "channel": name, "channel_url": url})
    return ch


def test_default_config_has_expected_keys():
    cfg = y.default_config("/tmp/lib")
    for key in ("hot_weeks", "budget_per_video", "budget_min_gb",
                "budget_max_gb", "audio_only_channels", "include_shorts",
                "subtitles", "verify_media", "pack_margin",
                "channel_budget_overrides", "settings_port",
                "inbox_channel_count", "inbox_playlist_count"):
        assert key in cfg, "missing config key: %s" % key


def test_budget_formula_scales_with_distinct_videos():
    cfg = y.default_config("/tmp/lib")
    cfg["budget_min_gb"] = 0.0
    ch = make_channel("Chan", ["a" * 11, "b" * 11, "c" * 11])
    got = y.channel_budget(cfg, ch) / 1e9
    expected = 3 * cfg["budget_per_video"]
    assert abs(got - expected) < 0.05


def test_budget_clamped_to_max():
    cfg = y.default_config("/tmp/lib")
    cfg["budget_max_gb"] = 1.0
    ch = make_channel("Chan", ["%011d" % i for i in range(60)])
    assert y.channel_budget(cfg, ch) <= 1.0 * 1024 ** 3 + 1


def test_budget_clamped_to_min():
    cfg = y.default_config("/tmp/lib")
    cfg["budget_min_gb"] = 2.0
    ch = make_channel("Chan", ["a" * 11])
    assert y.channel_budget(cfg, ch) >= 2.0 * 1024 ** 3 - 1


def test_channel_budget_override_by_name():
    cfg = y.default_config("/tmp/lib")
    cfg["channel_budget_overrides"] = {"Chan": 6.0}
    ch = make_channel("Chan", ["a" * 11])
    assert abs(y.channel_budget(cfg, ch) / 1e9 - 6.0 * 1024 ** 3 / 1e9) < 1


def test_channel_budget_override_by_url():
    cfg = y.default_config("/tmp/lib")
    cfg["channel_budget_overrides"] = {"https://x/c": 4.0}
    ch = make_channel("Chan", ["a" * 11], url="https://x/c")
    assert abs(y.channel_budget(cfg, ch) / 1e9 - 4.0 * 1024 ** 3 / 1e9) < 1


def test_override_never_clamped():
    cfg = y.default_config("/tmp/lib")
    cfg["budget_max_gb"] = 1.0
    cfg["channel_budget_overrides"] = {"Chan": 50.0}
    ch = make_channel("Chan", ["a" * 11])
    assert y.channel_budget(cfg, ch) > 10 * 1024 ** 3


def test_analyze_marks_hot_channels():
    cfg = y.default_config("/tmp/lib")
    now = y.now_utc()
    recs = []
    for i in range(6):
        recs.append({"id": "%011d" % i, "title": "t", "channel": "Hot",
                     "channel_url": "https://c/hot", "time": now.isoformat()})
    recs.append({"id": "x" * 11, "title": "t", "channel": "Cold",
                 "channel_url": "https://c/cold", "time": now.isoformat()})
    chans = y.analyze(cfg, recs, now)
    assert chans["https://c/hot"]["hot"] is True
    assert chans["https://c/cold"]["hot"] is False


def test_analyze_respects_exclude_channels():
    cfg = y.default_config("/tmp/lib")
    cfg["exclude_channels"] = ["Secret"]
    now = y.now_utc()
    recs = [{"id": "a" * 11, "title": "t", "channel": "Secret",
             "channel_url": "u", "time": now.isoformat()}]
    assert y.analyze(cfg, recs, now) == {}
