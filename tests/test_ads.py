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


def _run_main(monkeypatch, dest, state, extra_argv):
    """Invoke main() end-to-end with the network and downloads stubbed out."""
    import sys
    for name in ("enrich_channels", "download", "report", "rclone_pull",
                 "resolve_ad_videos", "inbox_download"):
        monkeypatch.setattr(y, name, lambda *a, **k: None)
    cfg = y.default_config(dest)
    cfg["ad_channel_names"] = []
    cfg["min_watches"] = 1
    cfgp = os.path.join(dest, "config.json")
    with open(cfgp, "w") as fh:
        json.dump(cfg, fh)
    monkeypatch.setattr(y, "CONFIG_PATH", cfgp)
    meta = os.path.join(dest, ".yosync")
    os.makedirs(meta, exist_ok=True)
    statepath = os.path.join(meta, "state.json")
    with open(statepath, "w") as fh:
        json.dump(state, fh)
    monkeypatch.setattr(sys, "argv", ["yosync", "--dest", dest] + extra_argv)
    y.main()
    with open(statepath) as fh:
        return json.load(fh)


def test_dry_run_never_deletes_ad_served_files(monkeypatch, tmp_path):
    """--dry-run is a preview: it must not touch the library, ads or not."""
    dest = str(tmp_path)
    f = os.path.join(dest, "Advertiser", "Ad [hhhhhhhhhhh].mp4")
    os.makedirs(os.path.dirname(f))
    open(f, "w").close()
    state = {
        "ad_landings": {"advertiser": "Advertiser"},
        "ad_videos": {"hhhhhhhhhhh": "2026-09-25T23:00:00Z"},
        "history": [{"id": "hhhhhhhhhhh", "title": "Ad",
                     "time": "2026-09-25T23:00:00+00:00",
                     "channel": "Advertiser",
                     "channel_url": "https://www.youtube.com/channel/uc_adv"}],
        "index": {"hhhhhhhhhhh": {"name": "Advertiser", "channel": "uc_adv",
                                  "path": f, "t": "2026-09-25"}},
    }
    out = _run_main(monkeypatch, dest, state, ["--dry-run"])
    assert os.path.exists(f), "dry run deleted a file"
    assert "hhhhhhhhhhh" in out["index"]


def test_dry_run_never_deletes_banned_channel_files(monkeypatch, tmp_path):
    dest = str(tmp_path)
    f = os.path.join(dest, "Banned", "Vid [iiiiiiiiiii].mp4")
    os.makedirs(os.path.dirname(f))
    open(f, "w").close()
    state = {
        "ad_landings": {"banned": "Banned"},
        "history": [{"id": "iiiiiiiiiii", "title": "Vid",
                     "time": "2026-09-25T23:00:00+00:00", "channel": "Banned",
                     "channel_url": "https://www.youtube.com/channel/uc_ban"}],
        "index": {"iiiiiiiiiii": {"name": "Banned", "channel": "uc_ban",
                                  "path": f, "t": "2026-09-25"}},
    }
    out = _run_main(monkeypatch, dest, state, ["--dry-run"])
    assert os.path.exists(f), "dry run deleted a banned-channel file"
    assert "iiiiiiiiiii" in out["index"]


# --- HTML watch-history: ad rows must not reach history ------------------------
# Older Takeout exports ship watch-history.html instead of .json. The ad pass
# and the normal pass match the same row shape, so the ad row used to be both
# remembered for purging *and* merged into history: the analyser then learned to
# mirror the advertiser, and purge_ad_videos saw a video as both ad-served and
# watched-on-purpose.
# NOTE: the parser captures exactly 11 chars, so ids here are 11 chars long.

def _html_row(video_id, when):
    return ('<div class="content-cell">Watched '
            'https://www.youtube.com/watch?v=%s</div>'
            '<div class="mdl-cell">%s</div>' % (video_id, when))


def _ad_html_row(video_id, when):
    return ('<div class="content-cell">From Google Ads</div>'
            + _html_row(video_id, when))


def test_html_ad_rows_are_collected_but_never_merged():
    html = (_ad_html_row("AdVideoId01", "Sep 25, 2026, 11:23:45 PM")
            + _html_row("RealVideo00", "Sep 25, 2026, 10:00:00 PM"))
    ad_videos = {}
    records = y.records_from_html(html, ads={}, ad_videos=ad_videos)

    assert "AdVideoId01" in ad_videos, "ad video should be tracked for purging"
    ids = [r["id"] for r in records]
    assert "RealVideo00" in ids, "real watch was dropped"
    assert "AdVideoId01" not in ids, "ad row leaked into history"


def test_html_shorts_ad_rows_are_skipped_too():
    html = ('<div class="content-cell">From Google Ads</div>'
            '<div class="content-cell">Watched '
            'https://www.youtube.com/shorts/ShrtsId0001</div>'
            '<div class="mdl-cell">Sep 25, 2026, 9:00:00 PM</div>')
    ad_videos = {}
    records = y.records_from_html(html, ads={}, ad_videos=ad_videos)
    assert list(ad_videos) == ["ShrtsId0001"]
    assert records == []


def test_html_without_ad_tracking_still_parses():
    """ad_videos=None (no ad tracking requested) must not crash."""
    html = _html_row("RealVideo00", "Sep 25, 2026, 10:00:00 PM")
    assert [r["id"] for r in y.records_from_html(html)] == ["RealVideo00"]


def test_html_ad_row_is_not_counted_as_a_watch():
    """End to end: an ad row must not make the analyser mirror a channel."""
    ad_videos = {}
    html = _ad_html_row("AdVideoId01", "Sep 25, 2026, 11:23:45 PM")
    records = y.records_from_html(html, ads={}, ad_videos=ad_videos)
    state = {}
    y.merge_history(state, records)
    assert not state.get("history"), "ad row counted as a watch"
    assert ad_videos, "but still tracked for purging"
