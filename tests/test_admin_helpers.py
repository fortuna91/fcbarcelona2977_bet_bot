import handlers


def test_is_admin_returns_true_for_known_id(monkeypatch):
    monkeypatch.setattr(handlers, "ADMIN_IDS", {111, 222})
    assert handlers.is_admin(111) is True


def test_is_admin_returns_false_for_unknown_id(monkeypatch):
    monkeypatch.setattr(handlers, "ADMIN_IDS", {111, 222})
    assert handlers.is_admin(333) is False


def test_is_admin_empty_set_always_false(monkeypatch):
    monkeypatch.setattr(handlers, "ADMIN_IDS", set())
    assert handlers.is_admin(111) is False
