"""yt-dlp argument construction, audio channels, and sidecar cleanup."""

import os
import tempfile

import helpers

y = helpers.load_yosync()


def test_video_args_contain_format_and_archive():
    cfg = y.default_config("/tmp/lib")
    args = y._download_args(cfg, "/tmp/arc")
    assert args[0] == "yt-dlp"
    assert y.FMT in args
    assert args[args.index("--download-archive") + 1] == "/tmp/arc"
    assert "--merge-output-format" in args


def test_audio_args_use_mp3_extraction():
    cfg = y.default_config("/tmp/lib")
    args = y._download_args(cfg, "/tmp/arc", audio=True)
    assert "-x" in args
    assert args[args.index("--audio-format") + 1] == "mp3"
    assert args[args.index("-o") + 1].endswith(".mp3")


def test_subtitles_flag_adds_write_subs():
    cfg = y.default_config("/tmp/lib")
    cfg["subtitles"] = True
    cfg["subtitle_langs"] = ["en", "pt"]
    args = y._download_args(cfg, "/tmp/arc")
    assert "--write-subs" in args
    assert args[args.index("--sub-langs") + 1] == "en,pt"


def test_subtitles_off_by_default():
    cfg = y.default_config("/tmp/lib")
    assert "--write-subs" not in y._download_args(cfg, "/tmp/arc")


def test_shorts_toggle_adds_match_filter():
    cfg = y.default_config("/tmp/lib")
    cfg["include_shorts"] = False
    args = y._download_args(cfg, "/tmp/arc")
    assert args[args.index("--match-filter") + 1] == "!duration<60"


def test_shorts_included_by_default():
    cfg = y.default_config("/tmp/lib")
    cfg["include_shorts"] = True
    assert "--match-filter" not in y._download_args(cfg, "/tmp/arc")


def test_is_audio_channel_by_name():
    cfg = y.default_config("/tmp/lib")
    cfg["audio_only_channels"] = ["Podcast One"]
    assert y._is_audio_channel(cfg, {"name": "Podcast One"}) is True
    assert y._is_audio_channel(cfg, {"name": "Other"}) is False


def test_is_audio_channel_by_url():
    cfg = y.default_config("/tmp/lib")
    cfg["audio_only_channels"] = ["https://youtube.com/@x"]
    ch = {"name": "X", "url": "https://youtube.com/@x"}
    assert y._is_audio_channel(cfg, ch) is True


def test_is_audio_channel_empty_list():
    cfg = y.default_config("/tmp/lib")
    cfg["audio_only_channels"] = []
    assert y._is_audio_channel(cfg, {"name": "Anything"}) is False


def test_remove_with_sidecars_cleans_subtitles():
    d = tempfile.mkdtemp()
    base = os.path.join(d, "Title [abcdefghijk]")
    for ext in (".mp4", ".en.srt", ".en.vtt"):
        open(base + ext, "w").close()
    removed = y._remove_with_sidecars(base + ".mp4")
    assert removed == 3
    assert os.listdir(d) == []


def test_remove_with_sidecars_leaves_unrelated_files():
    d = tempfile.mkdtemp()
    keep = os.path.join(d, "Other Video [zzzzzzzzzzz].mp4")
    open(keep, "w").close()
    open(os.path.join(d, "Title [abcdefghijk].mp4"), "w").close()
    y._remove_with_sidecars(os.path.join(d, "Title [abcdefghijk].mp4"))
    assert os.listdir(d) == [os.path.basename(keep)]


def test_reconcile_index_picks_up_mp3_and_video():
    dest = tempfile.mkdtemp()
    folder = os.path.join(dest, "Chan")
    os.makedirs(folder)
    open(os.path.join(folder, "V [aaaaaaaaaaa].mp4"), "w").close()
    open(os.path.join(folder, "A [bbbbbbbbbbb].mp3"), "w").close()
    cfg = y.default_config(dest)
    index = {}
    y.reconcile_index(cfg, index, {}, True)
    assert set(index.keys()) == {"aaaaaaaaaaa", "bbbbbbbbbbb"}


def test_reconcile_index_skips_inbox_and_state_dirs():
    dest = tempfile.mkdtemp()
    for sub in (".yosync", "inbox"):
        folder = os.path.join(dest, sub, "Chan")
        os.makedirs(folder)
        open(os.path.join(folder, "V [ccccccccccc].mp4"), "w").close()
    cfg = y.default_config(dest)
    index = {}
    y.reconcile_index(cfg, index, {}, True)
    assert index == {}
