"""Integrity check (--verify) and inbox URL handling."""

import json
import os
import time

import helpers

y = helpers.load_yosync()


def make_lib():
    import tempfile
    return tempfile.mkdtemp(prefix="yosync-verify-")


def write_index(dest, entries):
    sdir = os.path.join(dest, ".yosync")
    os.makedirs(sdir, exist_ok=True)
    state = {"index": entries, "video_cache": {}}
    with open(os.path.join(sdir, "state.json"), "w") as fh:
        json.dump(state, fh)
    with open(os.path.join(sdir, "dl-archive.txt"), "w") as fh:
        fh.write("youtube abc12345678\n")
    return state


def test_verify_removes_missing_file_from_index():
    dest = make_lib()
    missing = os.path.join(dest, "Chan", "Gone [abc12345678].mp4")
    state = write_index(dest, {"abc12345678": {
        "channel": "k", "name": "Chan", "path": missing, "t": "2026-01-01"}})
    cfg = y.default_config(dest)
    y.verify_media(cfg, state, True)
    assert "abc12345678" not in state["index"]


def test_verify_unarchives_broken_video():
    dest = make_lib()
    folder = os.path.join(dest, "Chan")
    os.makedirs(folder)
    bad = os.path.join(folder, "Bad [abc12345678].mp4")
    open(bad, "w").write("x")
    state = write_index(dest, {"abc12345678": {
        "channel": "k", "name": "Chan", "path": bad, "t": "2026-01-01"}})
    cfg = y.default_config(dest)
    cfg["verify_min_size_mb"] = 100
    y.verify_media(cfg, state, True)
    archive = open(os.path.join(dest, ".yosync", "dl-archive.txt")).read()
    assert "abc12345678" not in archive
    assert not os.path.exists(bad)


def test_verify_keeps_file_passing_size_check(monkeypatch):
    """Size-fallback path (no ffprobe): a big-enough file survives."""
    monkeypatch.setattr(y.shutil, "which", lambda name: None)
    dest = make_lib()
    folder = os.path.join(dest, "Chan")
    os.makedirs(folder)
    good = os.path.join(folder, "Good [aaaaaaaaaaa].mp4")
    with open(good, "wb") as fh:
        fh.write(b"x" * (2 * 1024 * 1024))
    state = write_index(dest, {"aaaaaaaaaaa": {
        "channel": "k", "name": "Chan", "path": good, "t": "2026-01-01"}})
    cfg = y.default_config(dest)
    cfg["verify_min_size_mb"] = 1
    y.verify_media(cfg, state, True)
    assert os.path.exists(good)
    assert "aaaaaaaaaaa" in state["index"]


def test_verify_removes_file_failing_size_check(monkeypatch):
    monkeypatch.setattr(y.shutil, "which", lambda name: None)
    dest = make_lib()
    folder = os.path.join(dest, "Chan")
    os.makedirs(folder)
    small = os.path.join(folder, "Small [bbbbbbbbbbb].mp4")
    open(small, "w").write("x")
    state = write_index(dest, {"bbbbbbbbbbb": {
        "channel": "k", "name": "Chan", "path": small, "t": "2026-01-01"}})
    cfg = y.default_config(dest)
    cfg["verify_min_size_mb"] = 1
    y.verify_media(cfg, state, True)
    assert not os.path.exists(small)
    assert "bbbbbbbbbbb" not in state["index"]


def test_ffprobe_ok_returns_bool_or_none():
    import shutil as _shutil
    import tempfile
    d = tempfile.mkdtemp()
    junk = os.path.join(d, "junk.mp4")
    with open(junk, "w") as fh:
        fh.write("not media")
    if _shutil.which("ffprobe"):
        assert y._ffprobe_ok(junk) is False
    else:
        assert y._ffprobe_ok(junk) is None


def test_verify_reconciles_unindexed_files():
    dest = make_lib()
    folder = os.path.join(dest, "Chan")
    os.makedirs(folder)
    open(os.path.join(folder, "New [ddddddddddd].mp4"), "w").close()
    state = write_index(dest, {})
    cfg = y.default_config(dest)
    y.verify_media(cfg, state, True)
    assert "ddddddddddd" in state["index"]


def test_verify_cleans_stale_partials():
    dest = make_lib()
    folder = os.path.join(dest, "Chan")
    os.makedirs(folder)
    part = os.path.join(folder, "V [eeeeeeeeeee].mp4.part")
    open(part, "w").close()
    old = time.time() - 3 * 86400
    os.utime(part, (old, old))
    state = write_index(dest, {})
    cfg = y.default_config(dest)
    y.verify_media(cfg, state, True)
    assert not os.path.exists(part)


def test_discard_archive_handles_both_formats():
    lines = {"abc12345678", "youtube def12345678", "YouTube ghi12345678"}
    y._discard_archive(lines, "abc12345678")
    y._discard_archive(lines, "def12345678")
    y._discard_archive(lines, "ghi12345678")
    assert lines == set()


def test_url_kind_classification():
    assert y._url_kind("https://www.youtube.com/watch?v=abc12345678") == "video"
    assert y._url_kind("https://www.youtube.com/@Chan") == "channel"
    assert y._url_kind("https://www.youtube.com/channel/UC1") == "channel"
    assert y._url_kind("https://www.youtube.com/playlist?list=PL1") == "playlist"


def test_inbox_targets_reads_txt_and_ignores_zip():
    dest = make_lib()
    inbox = os.path.join(dest, "inbox")
    os.makedirs(inbox)
    with open(os.path.join(inbox, "links.txt"), "w") as fh:
        fh.write("watch this https://www.youtube.com/watch?v=abc12345678\n"
                 "and this @SomeChannel\n")
    open(os.path.join(inbox, "archive.zip"), "w").close()
    targets = y._inbox_targets(y.default_config(dest))
    assert len(targets) == 2
    assert "watch?v=abc12345678" in targets[0]["url"]
    assert targets[1]["url"] == "https://www.youtube.com/@SomeChannel"


def test_inbox_targets_ignores_dotfiles():
    dest = make_lib()
    inbox = os.path.join(dest, "inbox")
    os.makedirs(inbox)
    with open(os.path.join(inbox, ".hidden"), "w") as fh:
        fh.write("https://www.youtube.com/watch?v=abc12345678\n")
    assert y._inbox_targets(y.default_config(dest)) == []


def _cfg_for_inbox(dest):
    cfg = y.default_config(dest)
    y.ensure_dirs(cfg)
    return cfg


def _fake_ytdlp(monkeypatch, returncode, stdout="", stderr=""):
    def fake_run(cmd, **kwargs):
        return type("R", (), {"returncode": returncode, "stdout": stdout,
                              "stderr": stderr})()

    monkeypatch.setattr(y.subprocess, "run", fake_run)


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()
    return path


def test_inbox_failure_leaves_file_for_retry(monkeypatch):
    """A failed yt-dlp run must not consume the input file."""
    dest = make_lib()
    inbox = os.path.join(dest, "inbox")
    os.makedirs(inbox)
    src = os.path.join(inbox, "links.txt")
    with open(src, "w") as fh:
        fh.write("https://www.youtube.com/watch?v=abc12345678\n")
    _fake_ytdlp(monkeypatch, 1)
    y.inbox_download(_cfg_for_inbox(dest), True, {})
    assert os.path.exists(src)
    assert not os.path.exists(os.path.join(dest, ".yosync", "inbox-consumed", "links.txt"))


def test_inbox_indexes_destination_from_yt_dlp_log(monkeypatch):
    """yt-dlp writes progress to stderr; the path must still be indexed."""
    dest = make_lib()
    inbox = os.path.join(dest, "inbox")
    os.makedirs(inbox)
    src = os.path.join(inbox, "links.txt")
    with open(src, "w") as fh:
        fh.write("https://www.youtube.com/watch?v=abc12345678\n")
    out = _touch(os.path.join(dest, "Chan", "Title [abc12345678].mp4"))
    _fake_ytdlp(monkeypatch, 0,
                stderr="[download] Destination: %s\n" % out)
    state = {"index": {}}
    n = y.inbox_download(_cfg_for_inbox(dest), True, state)
    assert n == 1
    assert state["index"]["abc12345678"]["path"] == out
    assert not os.path.exists(src)
    assert os.path.exists(os.path.join(dest, ".yosync", "inbox-consumed", "links.txt"))


def test_inbox_ignores_non_existent_destination(monkeypatch):
    dest = make_lib()
    inbox = os.path.join(dest, "inbox")
    os.makedirs(inbox)
    with open(os.path.join(inbox, "links.txt"), "w") as fh:
        fh.write("https://www.youtube.com/watch?v=abc12345678\n")
    ghost = os.path.join(dest, "Chan", "Gone [abc12345678].mp4")
    _fake_ytdlp(monkeypatch, 0, "[download] Destination: %s\n" % ghost)
    state = {"index": {}}
    assert y.inbox_download(_cfg_for_inbox(dest), True, state) == 0
    assert state["index"] == {}
