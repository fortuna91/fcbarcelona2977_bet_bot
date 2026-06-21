def calculate_points_breakdown(
    bet_h: int, bet_g: int, actual_h: int, actual_g: int
) -> tuple[int, list[str]]:
    """Return (total_points, earned_category_labels) with Russian descriptions."""
    points = 0
    earned = []

    bet_res = (bet_h > bet_g) - (bet_h < bet_g)
    act_res = (actual_h > actual_g) - (actual_h < actual_g)
    if bet_res == act_res:
        points += 2
        earned.append("+2 за исход матча")

    if bet_h == actual_h:
        points += 1
        earned.append("+1 за счёт хозяев")

    if bet_g == actual_g:
        points += 1
        earned.append("+1 за счёт гостей")

    if (bet_h - bet_g) == (actual_h - actual_g):
        points += 1
        earned.append("+1 за разницу мячей")

    if (bet_h + bet_g) == (actual_h + actual_g):
        points += 1
        earned.append("+1 за общий счёт")

    return points, earned


def calculate_points(bet_h: int, bet_g: int, actual_h: int, actual_g: int) -> int:
    """Calculate total points (delegates to calculate_points_breakdown)."""
    pts, _ = calculate_points_breakdown(bet_h, bet_g, actual_h, actual_g)
    return pts
