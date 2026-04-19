from points_calculator import calculate_points

def test_calculate_points_full_match():
    # Exact match: 2 (outcome) + 1 (home) + 1 (guest) + 1 (diff) + 1 (total) = 6
    assert calculate_points(2, 1, 2, 1) == 6

def test_calculate_points_outcome_and_diff():
    # Outcome: Win (2)
    # Home: 2 != 1 (0)
    # Guest: 1 != 0 (0)
    # Diff: (2-1) == (1-0) = 1 (1)
    # Total: (2+1) != (1+0) (0)
    # Total = 2 + 1 = 3
    assert calculate_points(2, 1, 1, 0) == 3

def test_calculate_points_outcome_only():
    # Outcome: Win (2)
    # Home: 2 != 3 (0)
    # Guest: 1 != 0 (0)
    # Diff: 1 != 3 (0)
    # Total: 3 != 3 (1) -- wait, 2+1=3 and 3+0=3. Total is same.
    # Total = 2 + 1 = 3
    assert calculate_points(2, 1, 3, 0) == 3

def test_calculate_points_outcome_only_no_total():
    # Outcome: Win (2)
    # Home: 4 != 2 (0)
    # Guest: 1 != 0 (0)
    # Diff: 3 != 2 (0)
    # Total: 5 != 2 (0)
    # Total = 2
    assert calculate_points(4, 1, 2, 0) == 2

def test_calculate_points_draw_exact():
    # Exact match: 2 (outcome) + 1 (home) + 1 (guest) + 1 (diff) + 1 (total) = 6
    assert calculate_points(1, 1, 1, 1) == 6

def test_calculate_points_draw_diff():
    # Outcome: Draw (2)
    # Home: 1 != 2 (0)
    # Guest: 1 != 2 (0)
    # Diff: 0 == 0 (1)
    # Total: 2 != 4 (0)
    # Total = 2 + 1 = 3
    assert calculate_points(1, 1, 2, 2) == 3

def test_calculate_points_wrong_outcome():
    # Outcome: Loss vs Win (0)
    # Home: 1 == 1 (1)
    # Guest: 2 != 0 (0)
    # Diff: -1 != 1 (0)
    # Total: 3 != 1 (0)
    # Total = 1
    assert calculate_points(1, 2, 1, 0) == 1

def test_calculate_points_nothing():
    # Outcome: Win vs Loss (0)
    # Home: 2 != 0 (0)
    # Guest: 0 != 2 (0)
    # Diff: 2 != -2 (0)
    # Total: 2 != 2 (1) -- Total is same!
    # Total = 1
    assert calculate_points(2, 0, 0, 2) == 1
