import datetime
from models import Match
from handlers import decide_bet_action, format_match_button_label


def test_decide_bet_action_none():
    assert decide_bet_action([]) == "none"


def test_decide_bet_action_single():
    assert decide_bet_action([object()]) == "single"


def test_decide_bet_action_choose():
    assert decide_bet_action([object(), object()]) == "choose"


def test_format_match_button_label_converts_to_msk():
    # 18:00 UTC -> 21:00 Moscow (UTC+3)
    m = Match(
        id=1, title="ESP vs GER", start_time=datetime.datetime(2026, 6, 15, 18, 0)
    )
    assert format_match_button_label(m) == "21:00 ESP vs GER"
