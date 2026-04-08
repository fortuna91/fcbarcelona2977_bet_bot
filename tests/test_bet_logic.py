from datetime import datetime
from handlers import is_betting_allowed


def test_bet_timing():
    now = datetime(2024, 1, 1, 12, 0)
    
    # 10 mins before: True (allowed)
    assert is_betting_allowed(datetime(2024, 1, 1, 12, 10), now) is True
    
    # 5 mins before: False (too late)
    # The function uses (start_time - now) > timedelta(minutes=5)
    # 5 mins exactly is NOT > 5 mins, so it should be False.
    assert is_betting_allowed(datetime(2024, 1, 1, 12, 5), now) is False
    
    # 5 mins 1 sec before: True
    assert is_betting_allowed(datetime(2024, 1, 1, 12, 5, 1), now) is True
    
    # 1 min before: False
    assert is_betting_allowed(datetime(2024, 1, 1, 12, 1), now) is False
    
    # Started: False
    assert is_betting_allowed(datetime(2024, 1, 1, 11, 59), now) is False
