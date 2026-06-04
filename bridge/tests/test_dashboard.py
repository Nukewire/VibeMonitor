from vibemonitor.config import Config
from vibemonitor.model import Store
from vibemonitor.hub import create_app

CFG = Config(token="secret", working_sec=10, waiting_ttl_sec=1800, gone_ttl_sec=1800)
H = {"X-VibeMonitor-Token": "secret"}


def make_client(store, usage=None, summary_provider=None):
    app = create_app(store, CFG, usage_provider=lambda: (usage or {"claude": {}, "codex": {}}),
                     clock=lambda: 1005.0, summary_provider=summary_provider)
    app.testing = True
    return app.test_client()


def test_dashboard_served_as_html():
    r = make_client(Store()).get("/")
    assert r.status_code == 200
    assert r.mimetype == "text/html"


def test_dashboard_contains_shell_and_js_wiring():
    body = make_client(Store()).get("/").get_data(as_text=True)
    # proves the page shell + the JS that talks to the data API is present
    assert "VibeMonitor" in body
    assert "/state" in body
    assert "X-VibeMonitor-Token" in body


def test_dashboard_needs_no_token():
    # the shell is unauthenticated; it carries no data, so no token header is required
    r = make_client(Store()).get("/")              # no H header
    assert r.status_code == 200


def test_state_still_requires_token():
    # guards the contract: the data API must stay token-gated
    assert make_client(Store()).get("/state").status_code == 401


def test_dashboard_wires_analytics_view():
    body = make_client(Store()).get("/").get_data(as_text=True)
    # proves the Analytics view toggle + its /analytics fetch are present in the shell
    assert "/analytics" in body
    assert "Analytics" in body


def test_dashboard_wires_new_features():
    body = make_client(Store()).get("/").get_data(as_text=True)
    # proves the new feature wiring is present in the shell:
    # spend section fetches /costs, capacity advisor reads `capacity`,
    # and waiting-row escalation reads `waitingSec`
    assert "/costs" in body
    assert "capacity" in body
    assert "waitingSec" in body
