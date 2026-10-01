"""An ad is not proof you dislike the channel. Never delete a watched one.

Regression tests for a real incident: resolving ad videos filled ad_landings
with 91 real advertiser names, and the wholesale channel purge then deleted 9
legitimate videos (8 from a brand channel watched 33 times, 1 from a channel
whose two-letter name is shared by hundreds of other watches).
"""

import json
import os

import helpers

y = helpers.load_yosync()


def _lib(tmp_path, files):
    """files: {video_id: (channel_key, name)} -> real files on disk."""
    dest = str(tmp_path)
    index = {}
    for vid, (key, name) in files.items():
        p = os.path.join(dest, name, "v%s.mp4" % vid)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").close()
        index[vid] = {"name": name, "channel": key, "path": p, "t": "2026-09-25"}
    return dest, index


def test_watched_channel_survives_ad_landing(tmp_path):
    """The brand channel that serves ads but is genuinely watched stays put."""
    dest, index = _lib(tmp_path, {
        "aaaaaaaaaaa": ("uc_brand", "BigBrand"),
        "bbbbbbbbbbb": ("uc_adv", "PureAdvertiser"),
    })
    state = {
        "ad_landings": {"bigbrand": "BigBrand", "pureadvertiser": "PureAdvertiser"},
        "history": [{"id": "aaaaaaaaaaa", "channel": "BigBrand",
                     "channel_url": "https://www.youtube.com/channel/uc_brand"}],
    }
    removed = y.purge_ad_channels(y.default_config(dest), {}, index, True, state)
    assert removed == 1, "only the ad-only advertiser channel should go"
    assert "aaaaaaaaaaa" in index, "a genuinely watched video was deleted"
    assert os.path.exists(index["aaaaaaaaaaa"]["path"])
    assert "bbbbbbbbbbb" not in index


def test_organic_channel_url_protects_even_with_shared_name(tmp_path):
    """Name collisions must not matter: match organic history by channel URL."""
    dest, index = _lib(tmp_path, {"ccccccccccc": ("uc_one", "Two")})
    state = {
        "ad_landings": {"two": "Two"},
        "history": [{"id": "ccccccccccc", "channel": "Two",
                     "channel_url": "https://www.youtube.com/channel/uc_one"}],
    }
    y.purge_ad_channels(y.default_config(dest), {}, index, True, state)
    assert "ccccccccccc" in index


def test_ad_keyword_cannot_purge_a_watched_channel(tmp_path):
    dest, index = _lib(tmp_path, {"ddddddddddd": ("uc_food", "Chef")})
    cfg = y.default_config(dest)
    cfg["ad_keywords"] = ["chef"]
    state = {"ad_landings": {},
             "history": [{"id": "ddddddddddd", "channel": "Chef",
                          "channel_url": "https://www.youtube.com/channel/uc_food"}]}
    assert y.purge_ad_channels(cfg, {}, index, True, state) == 0
    assert "ddddddddddd" in index


def test_explicit_ad_channel_names_still_wins(tmp_path):
    """Naming a channel in config is explicit intent, so it is honoured."""
    dest, index = _lib(tmp_path, {"eeeeeeeeeee": ("uc_x", "Wanted")})
    cfg = y.default_config(dest)
    cfg["ad_channel_names"] = ["Wanted"]
    state = {"history": [{"id": "eeeeeeeeeee", "channel": "Wanted",
                          "channel_url": "https://www.youtube.com/channel/uc_x"}]}
    assert y.purge_ad_channels(cfg, {}, index, True, state) == 1
    assert "eeeeeeeeeee" not in index


def test_purge_does_not_rewrite_config_exclude_channels(tmp_path):
    """The incident also pushed purged names into exclude_channels, which
    would silently stop the user ever downloading that channel again."""
    dest, index = _lib(tmp_path, {"fffffffffff": ("uc_adv", "Advertiser")})
    cfg = y.default_config(dest)
    cfgp = os.path.join(dest, "config.json")
    with open(cfgp, "w") as fh:
        json.dump(cfg, fh)
    y.CONFIG_PATH = cfgp
    state = {"ad_landings": {"advertiser": "Advertiser"}, "history": []}
    assert y.purge_ad_channels(cfg, {}, index, True, state) == 1
    assert cfg.get("exclude_channels") == [], "config was silently polluted"
    assert state.get("ad_purged_channels") == ["Advertiser"]


def test_video_level_purge_is_the_safe_mechanism(tmp_path):
    """Ad videos that were never watched organically do get removed."""
    dest, index = _lib(tmp_path, {"ggggggggggg": ("uc_adv", "Advertiser")})
    state = {"ad_videos": {"ggggggggggg": "2026-09-25T23:00:00Z"},
             "history": [{"id": "hhhhhhhhhhh", "channel": "Other"}]}
    assert y.purge_ad_videos({}, index, True, state) == 1
    assert index == {}


def test_end_to_end_ingest_cannot_delete_watched_videos(tmp_path, monkeypatch):
    """The full main() pipeline with resolved ad channels present."""
    dest, index = _lib(tmp_path, {
        "iiiiiiiiiii": ("uc_brand", "BigBrand"),
        "jjjjjjjjjjj": ("uc_adv", "PureAdvertiser"),
    })
    state = {
        "ad_landings": {"bigbrand": "BigBrand", "pureadvertiser": "PureAdvertiser"},
        "history": [{"id": "iiiiiiiiiii", "title": "t", "time": "2026-09-25T23:00:00+00:00",
                     "channel": "BigBrand",
                     "channel_url": "https://www.youtube.com/channel/uc_brand"}],
        "index": index,
    }
    for name in ("enrich_channels", "download", "report", "rclone_pull",
                 "resolve_ad_videos", "inbox_download"):
        monkeypatch.setattr(y, name, lambda *a, **k: None)
    cfg = y.default_config(dest)
    cfgp = os.path.join(dest, "config.json")
    with open(cfgp, "w") as fh:
        json.dump(cfg, fh)
    monkeypatch.setattr(y, "CONFIG_PATH", cfgp)
    os.makedirs(os.path.join(dest, ".yosync"), exist_ok=True)
    with open(os.path.join(dest, ".yosync", "state.json"), "w") as fh:
        json.dump(state, fh)
    import sys
    monkeypatch.setattr(sys, "argv", ["yosync", "--dest", dest])
    y.main()
    with open(os.path.join(dest, ".yosync", "state.json")) as fh:
        out = json.load(fh)
    assert "iiiiiiiiiii" in out["index"], "main() deleted a watched video"
    assert os.path.exists(index["iiiiiiiiiii"]["path"])
