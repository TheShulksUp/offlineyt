"""Regression tests for the duplicate-copy bug ("Title [ID] 2.mp4").

Four separate defects let the same video sit on disk twice, and none of the
copies were ever visible to a later prune:

1. prune()/_trim_to_budget() forgot a download even when the unlink failed,
   so the next run re-downloaded it into yt-dlp's numbered variant.
2. reconcile_index() only matched "<title> [<id>].ext", so "[<id>] 2.mp4"
   was invisible forever -- nothing could ever reclaim it.
3. Both prune paths compared bare ids against "youtube <id>" archive lines,
   so no archive line was ever dropped.
4. Nothing re-registered on-disk videos that had drifted out of the archive,
   so yt-dlp considered them never-downloaded and fetched them again.
"""

import json
import os

from helpers import load_yosync, tmp_cfg

VID = "AbCdEfGhI12"   # placeholder video ID, not a real one


def _make(y, cfg, name, data=b"x" * 2048):
    ch = os.path.join(cfg["dest"], "Chan")
    os.makedirs(ch, exist_ok=True)
    path = os.path.join(ch, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def test_reconcile_index_sees_numbered_variants():
    """The ' 2' copy must be adopted instead of being invisible."""
    y = load_yosync()
    cfg = tmp_cfg(y)
    _make(y, cfg, "Some Title [%s].mp4" % VID)
    _make(y, cfg, "Some Title [%s] 2.mp4" % VID)
    index = {}
    assert y.reconcile_index(cfg, index, {}, True) == 1
    # canonical name wins, not the numbered one
    assert index[VID]["path"].endswith("[%s].mp4" % VID)


def test_reconcile_index_rescues_orphan_numbered_copy():
    """With only a numbered copy on disk it must still be indexed."""
    y = load_yosync()
    cfg = tmp_cfg(y)
    _make(y, cfg, "Some Title [%s] 2.mp4" % VID)
    index = {}
    assert y.reconcile_index(cfg, index, {}, True) == 1
    assert index[VID]["path"].endswith("2.mp4")


def test_reconcile_index_ignores_fragments():
    """Pre-merge fragments are not playable videos and must stay out."""
    y = load_yosync()
    cfg = tmp_cfg(y)
    _make(y, cfg, "Some Title [%s].f298.mp4" % VID)
    index = {}
    assert y.reconcile_index(cfg, index, {}, True) == 0
    assert index == {}


def test_trim_keeps_archive_when_delete_fails():
    """A failed unlink must NOT forget the download (bug 1)."""
    y = load_yosync()
    cfg = tmp_cfg(y, channel_budget_gb=0.000001)
    path = _make(y, cfg, "Some Title [%s].mp4" % VID, b"y" * 4096)
    index = {VID: {"channel": "Chan", "name": "Chan", "path": path,
                   "t": "2026-01-01T00:00:00+00:00"}}
    archive_lines = {"youtube " + VID}
    # simulate iCloud refusing the delete
    y._remove_with_sidecars = lambda p: 0
    y._trim_to_budget(cfg, index, archive_lines, "Chan", 0, True)
    assert os.path.exists(path), "file must survive a failed delete"
    assert "youtube " + VID in archive_lines, \
        "archive line dropped despite the file still being on disk"
    assert VID in index, "index entry dropped despite the file still existing"


def test_trim_forgets_download_when_delete_succeeds():
    """The normal path must still forget a genuinely deleted video."""
    y = load_yosync()
    cfg = tmp_cfg(y, channel_budget_gb=0.000001)
    path = _make(y, cfg, "Some Title [%s].mp4" % VID, b"y" * 4096)
    index = {VID: {"channel": "Chan", "name": "Chan", "path": path,
                   "t": "2026-01-01T00:00:00+00:00"}}
    archive_lines = {"youtube " + VID}
    y._trim_to_budget(cfg, index, archive_lines, "Chan", 0, True)
    assert not os.path.exists(path)
    assert archive_lines == set()
    assert index == {}


def test_trim_drops_prefixed_archive_line():
    """Archive lines look like 'youtube <id>'; the bare id must match too."""
    y = load_yosync()
    cfg = tmp_cfg(y, channel_budget_gb=0.000001)
    path = _make(y, cfg, "Some Title [%s].mp4" % VID, b"y" * 4096)
    index = {VID: {"channel": "Chan", "name": "Chan", "path": path,
                   "t": "2026-01-01T00:00:00+00:00"}}
    archive_lines = {"youtube " + VID}
    y._trim_to_budget(cfg, index, archive_lines, "Chan", 0, True)
    assert "youtube " + VID not in archive_lines


def test_prune_drops_prefixed_archive_line():
    """Same for prune(): bare-id filtering never matched (bug 3)."""
    y = load_yosync()
    cfg = tmp_cfg(y, cold_days=0, stale_grace_days=10**6)
    path = _make(y, cfg, "Some Title [%s].mp4" % VID, b"y" * 4096)
    index = {VID: {"channel": "https://c/Chan", "name": "Chan", "path": path,
                   "t": "2026-01-01T00:00:00+00:00"}}
    archive_lines = {"youtube " + VID}
    channels = {"https://c/Chan": {"last": "2020-01-01T00:00:00+00:00"}}
    y.prune(cfg, channels, index, archive_lines, True,
            state={"last_ingest": "2026-01-01T00:00:00+00:00"})
    assert not os.path.exists(path)
    assert "youtube " + VID not in archive_lines, \
        "prune left the archive line behind; yt-dlp will never re-fetch it"


def test_verify_reregisters_ondisk_videos_in_archive():
    """A video on disk but absent from the archive must be re-registered."""
    y = load_yosync()
    cfg = tmp_cfg(y)
    path = _make(y, cfg, "Some Title [%s].mp4" % VID)
    archive = os.path.join(cfg["dest"], ".yosync", "dl-archive.txt")
    os.makedirs(os.path.dirname(archive), exist_ok=True)
    with open(archive, "w") as fh:
        fh.write("")            # archive lost/forgotten the entry
    state = {"index": {VID: {"channel": "Chan", "name": "Chan",
                             "path": path, "t": "2026-01-01T00:00:00+00:00"}}}
    y._ffprobe_ok = lambda p: True      # skip real ffprobe in tests
    y.verify_media(cfg, state, True)
    with open(archive) as fh:
        lines = {ln.strip() for ln in fh if ln.strip()}
    assert "youtube " + VID in lines, \
        "video on disk was left out of the archive; it will be re-downloaded"


def test_verify_keeps_archive_entry_when_corrupt_file_cannot_be_removed():
    """Bug 1 for the verify path: never forget an undeletable file."""
    y = load_yosync()
    cfg = tmp_cfg(y)
    path = _make(y, cfg, "Some Title [%s].mp4" % VID)
    archive = os.path.join(cfg["dest"], ".yosync", "dl-archive.txt")
    os.makedirs(os.path.dirname(archive), exist_ok=True)
    with open(archive, "w") as fh:
        fh.write("youtube " + VID)
    state = {"index": {VID: {"channel": "Chan", "name": "Chan",
                             "path": path, "t": "2026-01-01T00:00:00+00:00"}}}
    y._ffprobe_ok = lambda p: False     # file looks corrupt
    y._remove_with_sidecars = lambda p: 0  # but the delete fails
    y.verify_media(cfg, state, True)
    with open(archive) as fh:
        lines = {ln.strip() for ln in fh if ln.strip()}
    assert "youtube " + VID in lines
    assert VID in state["index"]


def test_scan_finds_duplicate_copies():
    y = load_yosync()
    cfg = tmp_cfg(y)
    _make(y, cfg, "Some Title [%s].mp4" % VID)
    _make(y, cfg, "Some Title [%s] 2.mp4" % VID)
    dupes, orphans, temps = y._scan_duplicate_copies(cfg)
    assert len(dupes) == 1
    vid, keep, drop = dupes[0]
    assert vid == VID
    assert keep.endswith("[%s].mp4" % VID), "must keep the canonical name"
    assert drop.endswith("2.mp4")


def test_scan_reports_fragments_and_temps():
    y = load_yosync()
    cfg = tmp_cfg(y)
    _make(y, cfg, "Some Title [%s].f298.mp4" % VID)
    _make(y, cfg, "Some Title [%s].f140-11.m4a.part" % VID)
    dupes, orphans, temps = y._scan_duplicate_copies(cfg)
    assert dupes == []
    assert len(orphans) == 1 and orphans[0][1].endswith(".f298.mp4")
    assert len(temps) == 1 and temps[0].endswith(".part")


def test_dedupe_dry_run_deletes_nothing():
    y = load_yosync()
    cfg = tmp_cfg(y)
    keep = _make(y, cfg, "Some Title [%s].mp4" % VID)
    drop = _make(y, cfg, "Some Title [%s] 2.mp4" % VID)
    state = {"index": {VID: {"channel": "Chan", "name": "Chan",
                             "path": keep, "t": "2026-01-01T00:00:00+00:00"}}}
    y.dedupe_library(cfg, state, apply=False, silent=True)
    assert os.path.exists(keep) and os.path.exists(drop)


def test_dedupe_apply_removes_only_the_copy():
    y = load_yosync()
    cfg = tmp_cfg(y)
    keep = _make(y, cfg, "Some Title [%s].mp4" % VID)
    drop = _make(y, cfg, "Some Title [%s] 2.mp4" % VID)
    state = {"index": {VID: {"channel": "Chan", "name": "Chan",
                             "path": keep, "t": "2026-01-01T00:00:00+00:00"}}}
    removed = y.dedupe_library(cfg, state, apply=True, silent=True)
    assert removed == 1
    assert os.path.exists(keep), "the real video must survive"
    assert not os.path.exists(drop)
    assert state["index"][VID]["path"] == keep


def test_dedupe_repoints_index_when_kept_copy_is_deleted():
    """If the indexed path is the redundant one, follow the survivor."""
    y = load_yosync()
    cfg = tmp_cfg(y)
    keep = _make(y, cfg, "Some Title [%s].mp4" % VID)
    drop = _make(y, cfg, "Some Title [%s] 2.mp4" % VID)
    state = {"index": {VID: {"channel": "Chan", "name": "Chan",
                             "path": drop, "t": "2026-01-01T00:00:00+00:00"}}}
    y.dedupe_library(cfg, state, apply=True, silent=True)
    assert os.path.exists(keep) and not os.path.exists(drop)
    assert state["index"][VID]["path"] == keep


def test_dedupe_apply_keeps_archive_entry_for_surviving_video():
    """After deleting the copy, the video is still on disk: keep it archived."""
    y = load_yosync()
    cfg = tmp_cfg(y)
    keep = _make(y, cfg, "Some Title [%s].mp4" % VID)
    drop = _make(y, cfg, "Some Title [%s] 2.mp4" % VID)
    archive = os.path.join(cfg["dest"], ".yosync", "dl-archive.txt")
    os.makedirs(os.path.dirname(archive), exist_ok=True)
    with open(archive, "w") as fh:
        fh.write("youtube " + VID)
    state = {"index": {VID: {"channel": "Chan", "name": "Chan",
                             "path": keep, "t": "2026-01-01T00:00:00+00:00"}}}
    y.dedupe_library(cfg, state, apply=True, silent=True)
    with open(archive) as fh:
        lines = {ln.strip() for ln in fh if ln.strip()}
    assert "youtube " + VID in lines, \
        "surviving video dropped out of the archive; it will be re-downloaded"