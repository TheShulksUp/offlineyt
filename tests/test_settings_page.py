"""Settings page: config coercion, validation, and HTTP API."""

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import helpers

y = helpers.load_yosync()


def test_schema_includes_all_new_features():
    keys = {f["key"] for g in y.SETTINGS_SCHEMA for f in g["fields"]}
    for key in ("dest", "audio_only_channels", "include_shorts",
                "subtitles", "channel_budget_overrides", "verify_media",
                "settings_port", "inbox_channel_count"):
        assert key in keys, "settings page missing field: %s" % key


def test_coerce_number_clamps_to_min_max():
    ft = {"key": "x", "type": "number", "min": 1, "max": 10}
    assert y._coerce_val(ft, 99) == 10
    assert y._coerce_val(ft, -5) == 1
    assert y._coerce_val(ft, "4.5") == 4.5


def test_coerce_bool_from_string():
    ft = {"key": "x", "type": "bool"}
    assert y._coerce_val(ft, "true") is True
    assert y._coerce_val(ft, "0") is False
    assert y._coerce_val(ft, True) is True


def test_coerce_list_from_newline_text():
    ft = {"key": "x", "type": "list"}
    assert y._coerce_val(ft, "a\n\n  b  \n") == ["a", "b"]


def test_coerce_map_from_lines():
    ft = {"key": "x", "type": "map"}
    assert y._coerce_val(ft, "Chan = 5.0\nBad\nOther=2") == {"Chan": 5.0,
                                                              "Other": 2.0}


def test_apply_update_rejects_unknown_key():
    cfg = y.default_config("/tmp/lib")
    _merged, errors = y._apply_config_update(cfg, {"not_a_key": 1})
    assert any("unknown key" in e for e in errors)


def test_apply_update_rejects_empty_dest():
    cfg = y.default_config("/tmp/lib")
    _merged, errors = y._apply_config_update(cfg, {"dest": "  "})
    assert any("library folder" in e for e in errors)


def test_apply_update_merges_and_keeps_untouched_keys():
    cfg = y.default_config("/tmp/lib")
    cfg["quickfill_workers"] = 8
    merged, errors = y._apply_config_update(cfg, {"budget_per_video": 0.25})
    assert not errors
    assert merged["budget_per_video"] == 0.25
    assert merged["quickfill_workers"] == 8
    assert merged["dest"] == cfg["dest"]


def test_schema_with_values_uses_config_values():
    cfg = y.default_config("/tmp/lib")
    cfg["budget_per_video"] = 0.33
    groups = y._schema_with_values(cfg)
    fields = {f["key"]: f["value"] for g in groups for f in g["fields"]}
    assert fields["budget_per_video"] == 0.33


class Server:
    """Run the real settings handler on a random free port."""

    def __init__(self, cfg):
        y.SELL["cfg"] = cfg
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        sock.close()
        cfg["settings_port"] = self.port
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port),
                                         y._SettingsHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)

    def __enter__(self):
        self.thread.start()
        time.sleep(0.2)
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def get(self, path):
        with urllib.request.urlopen(self.url(path), timeout=5) as r:
            return r.status, r.read().decode()

    def post(self, path, payload):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.url(path), data=data,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())


def test_http_index_serves_html():
    with Server(y.default_config("/tmp/lib")) as s:
        status, body = s.get("/")
        assert status == 200
        assert "OfflineYT" in body
        assert "__PORT__" not in body


def test_http_schema_endpoint():
    with Server(y.default_config("/tmp/lib")) as s:
        status, body = s.get("/api/schema")
        assert status == 200
        assert isinstance(json.loads(body), list)


def test_http_state_endpoint_shape():
    with Server(y.default_config("/tmp/lib")) as s:
        status, body = s.get("/api/state")
        assert status == 200
        data = json.loads(body)
        for k in ("dest", "history", "index", "hot", "free_gb"):
            assert k in data


def test_http_post_saves_config(tmp_path, monkeypatch):
    cfgdir = tmp_path / "cfg"
    cfgdir.mkdir()
    monkeypatch.setattr(y, "CONFIG_DIR", str(cfgdir))
    monkeypatch.setattr(y, "CONFIG_PATH", str(cfgdir / "config.json"))
    with Server(y.default_config("/tmp/lib")) as s:
        status, data = s.post("/api/config", {"budget_per_video": 0.42})
        assert status == 200 and data.get("ok") is True
    saved = json.load(open(str(cfgdir / "config.json")))
    assert saved["budget_per_video"] == 0.42


def test_http_post_bad_key_returns_400():
    with Server(y.default_config("/tmp/lib")) as s:
        status, data = s.post("/api/config", {"bogus": 1})
        assert status == 400 and "unknown key" in data["error"]


def test_http_unknown_path_404():
    with Server(y.default_config("/tmp/lib")) as s:
        try:
            s.get("/nope")
            raise AssertionError("expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
