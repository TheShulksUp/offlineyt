"""Ad detection: the new Takeout format carries no channel, only a video id."""

import json
import os

import helpers

y = helpers.load_yosync()

AD_TV = "From Google Ads"


def rec(vid, ad=False, **extra):
    e = {"header": "YouTube",
         "title": "Watched https://www.youtube.com/watch?v=" + vid,
         "time": "2026-09-25T23:00:00.000Z",
         "products": ["YouTube"],
         "activityControls": ["YouTube watch history"]}
    if ad:
        e["details"] = [{"name": AD_TV}]
    e.update(extra)
    return e


def test_new_format_ad_record_is_excluded_from_history():
    recs = y.records_from_json([rec("aaaaaaaaaaa"), rec("bbbbbbbbbbb", ad=True)])
    assert [r["id"] for r in recs] == ["aaaaaaaaaaa"]


def test_new_format_ad_video_id_is_captured():
    ads, adv = {}, {}
    y.records_from_json([rec("bbbbbbbbbbb", ad=True)], ads=ads, ad_videos=adv)
    assert list(adv) == ["bbbbbbbbbbb"]
    assert ads == {}


def test_old_format_ad_record_still_yields_channel_identifier():
    e = rec("ccccccccccc", ad=True,
            channelId="UCabcdefghijklmnopqrstuv",
            subtitles=[{"name": "SomeAdvertiser", "url": ""}])
    ads, adv = {}, {}
    y.records_from_json([e], ads=ads, ad_videos=adv)
    assert ads["someadvertiser"] == "SomeAdvertiser"
    # identifiers are stored lowercased so matching is case-insensitive
    assert "https://www.youtube.com/channel/ucabcdefghijklmnopqrstuv" in ads
    assert adv == {}, "old format has a channel already; no lookup needed"


def test_purge_removes_ad_only_video():
    dest = helpers.tmp_cfg(y)["dest"]
    os.makedirs(dest, exist_ok=True)
    f = os.path.join(dest, "Chan", "Ad [ddddddddddd].mp4")
    os.makedirs(os.path.dirname(f))
    open(f, "w").close()
    index = {"ddddddddddd": {"name": "Chan", "channel": "k", "path": f}}
    state = {"ad_videos": {"ddddddddddd": "2026-09-25T23:00:00Z"},
             "history": [{"id": "aaaaaaaaaaa", "channel": "X"}]}
    assert y.purge_ad_videos({}, index, True, state) == 1
    assert not os.path.exists(f)
    assert index == {}


def test_purge_keeps_video_also_watched_organically():
    """A channel you watch can also serve ads -- never delete those videos."""
    dest = helpers.tmp_cfg(y)["dest"]
    f = os.path.join(dest, "ShortName", "Real [eeeeeeeeeee].mp4")
    os.makedirs(os.path.dirname(f))
    open(f, "w").close()
    index = {"eeeeeeeeeee": {"name": "ShortName", "channel": "k", "path": f}}
    state = {"ad_videos": {"eeeeeeeeeee": "2026-09-25T23:00:00Z"},
             "history": [{"id": "eeeeeeeeeee", "channel": "ShortName"}]}
    assert y.purge_ad_videos({}, index, True, state) == 0
    assert os.path.exists(f)
    assert "eeeeeeeeeee" in index


def test_resolve_maps_ad_videos_to_channels(monkeypatch):
    def fake_batch(ids, sleep=0, timeout=60):
        return {"fffffffffff": {"channel": "SomeAdvertiser",
                                "channel_url": "https://www.youtube.com/channel/UCxyz"}}
    monkeypatch.setattr(y, "ytdlp_batch", fake_batch)
    state = {"ad_videos": {"fffffffffff": "2026-09-25T23:00:00Z"}}
    assert y.resolve_ad_videos(state, y.default_config("/tmp/lib"), True) == 1
    assert state["ad_landings"]["someadvertiser"] == "SomeAdvertiser"
    assert state["ad_landings"]["https://www.youtube.com/channel/ucxyz"] == \
        "https://www.youtube.com/channel/UCxyz"


def test_resolve_respects_limit_and_skips_resolved(monkeypatch):
    seen = []

    def fake_batch(ids, sleep=0, timeout=60):
        seen.append(list(ids))
        return {v: {"channel": "C" + v, "channel_url": None} for v in ids}

    monkeypatch.setattr(y, "ytdlp_batch", fake_batch)
    cfg = y.default_config("/tmp/lib")
    cfg["ad_resolve_limit"] = 2
    state = {"ad_videos": {"a1": "2026-01-02", "a2": "2026-01-03",
                           "a3": "2026-01-04"}}
    y.resolve_ad_videos(state, cfg, True)
    assert seen[0] == ["a3", "a2"], "newest first, capped at the limit"
    y.resolve_ad_videos(state, cfg, True)
    # the one leftover video is picked up next run; the resolved two are skipped
    assert seen[1] == ["a1"]
    y.resolve_ad_videos(state, cfg, True)
    assert len(seen) == 2, "everything resolved -> no more yt-dlp calls"
