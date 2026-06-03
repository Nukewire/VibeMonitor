from vibemonitor.summarycache import SummaryCache, hash_text


def test_needs_update_when_absent():
    c = SummaryCache()
    assert c.needs_update("sid1", "h1") is True


def test_needs_update_false_when_hash_matches():
    c = SummaryCache()
    c.set("sid1", "h1", "doing things")
    assert c.needs_update("sid1", "h1") is False


def test_needs_update_true_when_hash_differs():
    c = SummaryCache()
    c.set("sid1", "h1", "doing things")
    assert c.needs_update("sid1", "h2") is True


def test_get_returns_stored_summary():
    c = SummaryCache()
    c.set("sid1", "h1", "fixing tests")
    assert c.get("sid1") == "fixing tests"


def test_get_absent_returns_none():
    c = SummaryCache()
    assert c.get("nope") is None


def test_set_can_store_none_summary():
    c = SummaryCache()
    c.set("sid1", "h1", None)
    assert c.get("sid1") is None
    # stored hash still counts: no update needed for same hash
    assert c.needs_update("sid1", "h1") is False


def test_forget_removes_entry():
    c = SummaryCache()
    c.set("sid1", "h1", "x")
    c.forget("sid1")
    assert c.get("sid1") is None
    assert c.needs_update("sid1", "h1") is True


def test_forget_absent_is_noop():
    c = SummaryCache()
    c.forget("never")  # must not raise


def test_hash_text_stable():
    assert hash_text("hello") == hash_text("hello")


def test_hash_text_differs():
    assert hash_text("hello") != hash_text("world")


def test_hash_text_length():
    assert len(hash_text("anything")) == 16
