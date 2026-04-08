import pytest
from datetime import datetime, timedelta

def check_bet_timing(start_time, now):
    """Core logic for timing check"""
    if start_time <= now:
        return "too_late"
    if start_time - now <= timedelta(minutes=5):
        return "too_late"
    return "ok"

def test_bet_timing():
    now = datetime(2024, 1, 1, 12, 0)
    # 10 mins before: ok
    assert check_bet_timing(datetime(2024, 1, 1, 12, 10), now) == "ok"
    # 5 mins before: too_late
    assert check_bet_timing(datetime(2024, 1, 1, 12, 5), now) == "too_late"
    # 1 min before: too_late
    assert check_bet_timing(datetime(2024, 1, 1, 12, 1), now) == "too_late"
    # Started: too_late
    assert check_bet_timing(datetime(2024, 1, 1, 11, 59), now) == "too_late"
