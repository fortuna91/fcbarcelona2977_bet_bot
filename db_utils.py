import datetime
from sqlalchemy import select, func, desc
from models import User, Match, Bet

async def get_user(session, user_id):
    """Fetches a user by ID."""
    return await session.get(User, user_id)

async def get_next_match(session, now: datetime.datetime = None):
    """Fetches the next scheduled match."""
    if now is None:
        now = datetime.datetime.utcnow()
    stmt = select(Match).where(Match.status == 'NS', Match.start_time > now).order_by(Match.start_time.asc())
    return (await session.execute(stmt)).scalars().first()

async def get_upcoming_matches(session, limit=5, now: datetime.datetime = None):
    """Fetches upcoming matches."""
    if now is None:
        now = datetime.datetime.utcnow()
    stmt = select(Match).where(Match.start_time > now).order_by(Match.start_time.asc()).limit(limit)
    return (await session.execute(stmt)).scalars().all()

async def get_user_bet(session, user_id, match_id):
    """Fetches a bet for a user and match."""
    stmt = select(Bet).where(Bet.user_id == user_id, Bet.match_id == match_id)
    return (await session.execute(stmt)).scalar_one_or_none()

async def get_users_without_bet(session, match_id):
    """Fetches users who haven't placed a bet for a given match."""
    subquery = select(Bet.user_id).where(Bet.match_id == match_id)
    stmt = select(User).where(User.id.not_in(subquery))
    return (await session.execute(stmt)).scalars().all()

async def get_leaderboard(session):
    """Fetches the global leaderboard rankings."""
    stmt = select(User.display_name, User.username, User.id, func.sum(Bet.points_earned).label("total")).join(Bet).group_by(User.id).order_by(desc("total"))
    return (await session.execute(stmt)).all()
