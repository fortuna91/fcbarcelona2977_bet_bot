def calculate_points(bet_h: int, bet_g: int, actual_h: int, actual_g: int) -> int:
    """Calculate points based on cumulative rules."""
    points = 0
    
    # 1. Match Outcome (Win/Draw/Loss): 2 points
    bet_res = (bet_h > bet_g) - (bet_h < bet_g)
    act_res = (actual_h > actual_g) - (actual_h < actual_g)
    if bet_res == act_res:
        points += 2
        
    # 2. Exact Home Team Score: 1 point
    if bet_h == actual_h:
        points += 1
        
    # 3. Exact Guest Team Score: 1 point
    if bet_g == actual_g:
        points += 1
        
    # 4. Exact Goal Difference: 1 point
    if (bet_h - bet_g) == (actual_h - actual_g):
        points += 1
        
    # 5. Exact Total Goals: 1 point
    if (bet_h + bet_g) == (actual_h + actual_g):
        points += 1
        
    return points
