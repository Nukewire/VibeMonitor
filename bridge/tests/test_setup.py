from __future__ import annotations
import tomllib
from pathlib import Path

import pytest

from vibemonitor import setup
from vibemonitor.config import load_config


# --------------------------------------------------------------------------- #
# build_toml
# --------------------------------------------------------------------------- #

def _full_form():
    return {
        "token": "abc-123",
        "host": "0.0.0.0",
        "port": "5151",
        "enable_claude": True,
        "enable_codex": False,
        "summary_enabled": True,
        "summary_model": "google/gemma-4-31b-it:free",
        "summary_max_chars": 1500,
        "openrouter_api_key": "sk-or-v1-secret",
        "ha_webhook_url": "http://homeassistant.local:8123/api/webhook/vibemonitor-x",
        "push_provider": "ntfy",
        "push_ntfy_url": "https://ntfy.sh/vibemon-otter-ab12",
        "push_escalate_sec": 300,
        "pricing": {"claude-sonnet": {"input": 3.0, "output": 15.0}},
    }


def test_build_toml_round_trips_to_valid_config():
    text = setup.build_toml(_full_form())
    data = tomllib.loads(text)  # must parse
    assert data["token"] == "abc-123"
    assert data["host"] == "0.0.0.0"
    assert data["port"] == 5151
    assert data["providers"]["claude"] is True
    assert data["providers"]["codex"] is False
    assert data["summary"]["enabled"] is True
    assert data["summary"]["model"] == "google/gemma-4-31b-it:free"
    assert data["summary"]["max_chars"] == 1500
    assert data["openrouter"]["api_key"] == "sk-or-v1-secret"
    assert data["homeassistant"]["webhook_url"].endswith("vibemonitor-x")
    assert data["push"]["provider"] == "ntfy"
    assert data["push"]["ntfy_url"].endswith("ab12")
    assert data["push"]["escalate_sec"] == 300
    assert data["pricing"]["claude-sonnet"] == {"input": 3.0, "output": 15.0}
    # thresholds + poll defaults present
    assert data["thresholds"]["working_sec"] == 60
    assert data["poll"]["sessions_sec"] == 2.0


def test_build_toml_loads_via_config_loader(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(setup.build_toml(_full_form()), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.token == "abc-123"
    assert cfg.enable_codex is False
    assert cfg.summary_enabled is True
    assert cfg.openrouter_api_key == "sk-or-v1-secret"
    assert cfg.push_ntfy_url.endswith("ab12")
    assert cfg.pricing["claude-sonnet"] == {"input": 3.0, "output": 15.0}


def test_build_toml_omits_disabled_sections():
    form = {"token": "t", "summary_enabled": False, "push_provider": "ntfy"}  # no ntfy url
    text = setup.build_toml(form)
    data = tomllib.loads(text)
    assert "summary" not in data
    assert "openrouter" not in data
    assert "homeassistant" not in data
    assert "push" not in data       # ntfy selected but no url => omitted
    assert "pricing" not in data


def test_build_toml_minimal_only_token_and_providers():
    """All optional features off → a minimal but valid config with no optional
    sections. This is the 'skip everything' path from the wizard."""
    form = {
        "token": "minimal-tok",
        "host": "0.0.0.0",
        "port": 5151,
        "enable_claude": True,
        "enable_codex": True,
        # everything optional deliberately absent / falsy:
        "summary_enabled": False,
        "openrouter_api_key": "",
        "ha_webhook_url": "",
        "push_provider": "",
        "push_ntfy_url": "",
        "push_pushover_token": "",
        "push_pushover_user": "",
    }
    text = setup.build_toml(form)
    data = tomllib.loads(text)  # must parse
    # required pieces present
    assert data["token"] == "minimal-tok"
    assert data["host"] == "0.0.0.0"
    assert data["port"] == 5151
    assert data["providers"]["claude"] is True
    assert data["providers"]["codex"] is True
    assert data["thresholds"]["working_sec"] == 60
    assert data["poll"]["sessions_sec"] == 2.0
    # NO optional sections emitted
    for section in ("summary", "openrouter", "push", "homeassistant", "pricing"):
        assert section not in data, f"{section} should be omitted in minimal config"


def test_build_toml_minimal_loads_via_config_loader(tmp_path):
    """The minimal 'skip everything' config must be accepted by load_config."""
    form = {"token": "min-tok", "enable_claude": True, "enable_codex": True}
    p = tmp_path / "config.toml"
    p.write_text(setup.build_toml(form), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.token == "min-tok"
    assert cfg.enable_claude is True
    assert cfg.enable_codex is True
    # optional features defaulted off / empty
    assert cfg.summary_enabled is False
    assert cfg.openrouter_api_key is None
    assert cfg.ha_webhook_url is None
    assert cfg.push_ntfy_url is None
    assert cfg.push_pushover_token is None
    assert cfg.pricing == {}


def test_build_toml_pushover_section():
    form = {
        "token": "t",
        "push_provider": "pushover",
        "push_pushover_token": "ptok",
        "push_pushover_user": "puser",
    }
    data = tomllib.loads(setup.build_toml(form))
    assert data["push"]["provider"] == "pushover"
    assert data["push"]["pushover_token"] == "ptok"
    assert data["push"]["pushover_user"] == "puser"
    assert "ntfy_url" not in data["push"]


def test_build_toml_booleans_lowercase_and_strings_quoted():
    text = setup.build_toml({"token": "tok", "enable_claude": False})
    assert 'token = "tok"' in text
    assert "claude = false" in text
    assert "codex = true" in text


def test_build_toml_defaults_when_token_missing():
    text = setup.build_toml({})
    data = tomllib.loads(text)
    assert isinstance(data["token"], str) and data["token"]   # auto-generated


# --------------------------------------------------------------------------- #
# ha_snippets
# --------------------------------------------------------------------------- #

def test_ha_snippets_contains_ip_port_token_and_fields():
    snip = setup.ha_snippets("192.168.1.50", 5151, "tok-xyz")
    sensor = snip["sensor"]
    assert "192.168.1.50:5151/ha" in sensor
    assert "tok-xyz" in sensor
    for field in ("claude_pct", "codex_pct", "waiting_count", "any_waiting",
                  "longest_waiting_sec", "capacity_status", "stale_sec"):
        assert field in sensor
    assert "webhook" in snip["automation"]


# --------------------------------------------------------------------------- #
# local_ip
# --------------------------------------------------------------------------- #

def test_local_ip_returns_string_and_never_raises():
    ip = setup.local_ip()
    assert isinstance(ip, str)
    assert ip


# --------------------------------------------------------------------------- #
# Flask endpoints
# --------------------------------------------------------------------------- #

@pytest.fixture
def client(tmp_path):
    app = setup.create_setup_app(config_path=tmp_path / "config.toml")
    app.testing = True
    return app, app.test_client()


def test_index_serves_html(client):
    _, c = client
    r = c.get("/")
    assert r.status_code == 200
    assert r.mimetype == "text/html"
    assert "VibeMonitor" in r.get_data(as_text=True)


def test_defaults_endpoint(client):
    app, c = client
    r = c.get("/api/defaults")
    j = r.get_json()
    assert isinstance(j["token"], str) and j["token"]
    assert isinstance(j["local_ip"], str)
    assert j["ntfy_topic"].startswith("vibemon-")
    assert j["config_exists"] is False    # tmp path has no config yet


def test_save_writes_config_to_injected_path(client):
    app, c = client
    target = Path(app.config["CONFIG_PATH"])
    form = {
        "token": "save-tok",
        "host": "0.0.0.0",
        "port": 5151,
        "local_ip": "10.0.0.7",
        "enable_claude": True,
        "enable_codex": True,
    }
    r = c.post("/api/save", json=form)
    j = r.get_json()
    assert j["ok"] is True
    assert target.exists()
    cfg = load_config(target)
    assert cfg.token == "save-tok"
    # ha snippets prefilled with the device ip + port
    assert "10.0.0.7:5151/ha" in j["ha"]["sensor"]
    assert any("vibemonitor.main" in s for s in j["next_steps"])


def test_save_minimal_form_writes_loadable_config(client):
    """A minimal save (token + providers, every optional feature skipped/blank)
    must write a config that load_config accepts, with no optional sections."""
    app, c = client
    target = Path(app.config["CONFIG_PATH"])
    form = {
        "token": "skip-all-tok",
        "host": "0.0.0.0",
        "port": 5151,
        "enable_claude": True,
        "enable_codex": True,
        "summary_enabled": False,
        "openrouter_api_key": "",
        "ha_webhook_url": "",
        "push_provider": "",
        "push_ntfy_url": "",
        "push_pushover_token": "",
        "push_pushover_user": "",
    }
    r = c.post("/api/save", json=form)
    j = r.get_json()
    assert j["ok"] is True
    assert target.exists()
    data = tomllib.loads(target.read_text(encoding="utf-8"))
    for section in ("summary", "openrouter", "push", "homeassistant", "pricing"):
        assert section not in data
    cfg = load_config(target)
    assert cfg.token == "skip-all-tok"
    assert cfg.summary_enabled is False
    assert cfg.push_ntfy_url is None


def test_save_backs_up_existing_config(client):
    app, c = client
    target = Path(app.config["CONFIG_PATH"])
    target.write_text('token = "old"\n', encoding="utf-8")
    c.post("/api/save", json={"token": "new"})
    backup = target.with_suffix(".toml.bak")
    assert backup.exists()
    assert 'token = "old"' in backup.read_text(encoding="utf-8")
    assert load_config(target).token == "new"


def test_defaults_reports_existing_config(client):
    app, c = client
    Path(app.config["CONFIG_PATH"]).write_text('token = "x"\n', encoding="utf-8")
    assert c.get("/api/defaults").get_json()["config_exists"] is True


def test_test_openrouter_endpoint_mocked(client, monkeypatch):
    _, c = client
    monkeypatch.setattr(setup.summarizer, "summarize",
                        lambda *a, **k: "doing a thing")
    r = c.post("/api/test-openrouter", json={"api_key": "k", "model": "m"})
    assert r.get_json()["ok"] is True

    monkeypatch.setattr(setup.summarizer, "summarize", lambda *a, **k: None)
    r2 = c.post("/api/test-openrouter", json={"api_key": "k", "model": "m"})
    assert r2.get_json()["ok"] is False


def test_test_openrouter_requires_key(client):
    _, c = client
    assert c.post("/api/test-openrouter", json={"api_key": ""}).get_json()["ok"] is False


def test_test_ntfy_endpoint_mocked(client, monkeypatch):
    _, c = client
    sent = {}

    class FakeNotifier:
        def __init__(self, **kw):
            sent["url"] = kw.get("ntfy_url")
        def send(self, *a, **k):
            return True

    monkeypatch.setattr(setup, "PushNotifier", FakeNotifier)
    r = c.post("/api/test-ntfy", json={"ntfy_url": "https://ntfy.sh/topic"})
    assert r.get_json()["ok"] is True
    assert sent["url"] == "https://ntfy.sh/topic"


def test_test_ntfy_requires_url(client):
    _, c = client
    assert c.post("/api/test-ntfy", json={"ntfy_url": ""}).get_json()["ok"] is False
