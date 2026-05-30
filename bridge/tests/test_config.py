import textwrap
from vibemonitor.config import load_config, Config

def test_defaults_when_minimal(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('token = "secret"\n', encoding="utf-8")
    cfg = load_config(p)
    assert isinstance(cfg, Config)
    assert cfg.token == "secret"
    assert cfg.port == 8787
    assert cfg.working_sec == 60
    assert cfg.gone_ttl_sec == 14400
    assert cfg.claude_oauth_token is None
    assert cfg.poll_sessions_sec == 2.0

def test_overrides(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(textwrap.dedent('''
        token = "abc"
        port = 9000
        [thresholds]
        working_sec = 5
        gone_ttl_sec = 600
        [claude]
        oauth_token = "sk-xyz"
    '''), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.port == 9000
    assert cfg.working_sec == 5
    assert cfg.gone_ttl_sec == 600
    assert cfg.claude_oauth_token == "sk-xyz"

def test_missing_token_raises(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("port = 9000\n", encoding="utf-8")
    try:
        load_config(p)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "token" in str(e)


def test_waiting_ttl_and_gone_defaults(tmp_path):
    from vibemonitor.config import load_config
    p = tmp_path / "c.toml"
    p.write_text('token = "x"\n', encoding="utf-8")
    cfg = load_config(p)
    assert cfg.waiting_ttl_sec == 1800
    assert cfg.gone_ttl_sec == 14400      # now matches shipped config (4h), not old 30min
    assert cfg.working_sec == 60          # raised from 10 to reduce flicker
    assert not hasattr(cfg, "idle_sec")   # dead field removed


def test_waiting_ttl_read_from_thresholds(tmp_path):
    from vibemonitor.config import load_config
    p = tmp_path / "c.toml"
    p.write_text(
        'token = "x"\n[thresholds]\nwaiting_ttl_sec = 600\ngone_ttl_sec = 7200\n',
        encoding="utf-8")
    cfg = load_config(p)
    assert cfg.waiting_ttl_sec == 600
    assert cfg.gone_ttl_sec == 7200
