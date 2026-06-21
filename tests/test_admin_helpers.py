import datetime
from unittest.mock import MagicMock
import handlers
from handlers import get_forcechange_match_keyboard, get_forcechange_confirm_keyboard


def test_is_admin_returns_true_for_known_id(monkeypatch):
    monkeypatch.setattr(handlers, "ADMIN_IDS", {111, 222})
    assert handlers.is_admin(111) is True


def test_is_admin_returns_false_for_unknown_id(monkeypatch):
    monkeypatch.setattr(handlers, "ADMIN_IDS", {111, 222})
    assert handlers.is_admin(333) is False


def test_is_admin_empty_set_always_false(monkeypatch):
    monkeypatch.setattr(handlers, "ADMIN_IDS", set())
    assert handlers.is_admin(111) is False


def test_forcechange_match_keyboard_label_and_callback():
    m = MagicMock()
    m.id = 42
    m.start_time = datetime.datetime(2026, 6, 21, 18, 0)  # 21:00 MSK
    m.title = "Brazil vs Argentina"
    m.actual_home_score = 2
    m.actual_guest_score = 1

    kb = get_forcechange_match_keyboard([m])
    btn = kb.inline_keyboard[0][0]

    assert "21.06" in btn.text
    assert "Brazil vs Argentina" in btn.text
    assert "2:1" in btn.text
    assert btn.callback_data == "forcechange_pick:42"


def test_forcechange_match_keyboard_multiple_matches():
    matches = [MagicMock(id=i, start_time=datetime.datetime(2026, 6, i + 1, 18, 0),
                         title=f"Match {i}", actual_home_score=i, actual_guest_score=0)
               for i in range(1, 4)]
    kb = get_forcechange_match_keyboard(matches)
    assert len(kb.inline_keyboard) == 3


def test_forcechange_confirm_keyboard_yes_callback():
    kb = get_forcechange_confirm_keyboard(99, 3, 0)
    yes_btn = kb.inline_keyboard[0][0]
    assert yes_btn.callback_data == "confirm_forcechange:99:3:0"
    assert "Да" in yes_btn.text


def test_forcechange_confirm_keyboard_no_callback():
    kb = get_forcechange_confirm_keyboard(99, 3, 0)
    no_btn = kb.inline_keyboard[0][1]
    assert no_btn.callback_data == "cancel_forcechange"
    assert "Нет" in no_btn.text
