def calculate_points(bet_h: int, bet_g: int, actual_h: int, actual_g: int) -> int:
    """Calculate points based on cumulative rules."""
    points = 0
    
    # 1. Match Outcome (Win/Draw/Loss): 2 points
    bet_res = (bet_h > bet_g) - (bet_h < bet_g)
    act_res = (actual_h > actual_g) - (actual_h < actual_g)
    if bet_res == act_res:
        points += 2
        
    # 2. Exact Home Team Score: 3 points
    if bet_h == actual_h:
        points += 3
        
    # 3. Exact Guest Team Score: 3 points
    if bet_g == actual_g:
        points += 3
        
    # 4. Exact Goal Difference: 4 points
    if (bet_h - bet_g) == (actual_h - actual_g):
        points += 4
        
    # 5. Exact Total Goals: 4 points
    if (bet_h + bet_g) == (actual_h + actual_g):
        points += 4
        
    return points
