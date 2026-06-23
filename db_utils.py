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
    stmt = (
        select(Match)
        .where(
            Match.status == "NS", Match.start_time > now, Match.title != "None vs None"
        )
        .order_by(Match.start_time.asc())
    )
    return (await session.execute(stmt)).scalars().first()


async def get_matches_on_day(session, day: datetime.date):
    """Fetches all matches on a specific date, ordered by start time."""
    stmt = (
        select(Match)
        .where(func.date(Match.start_time) == day)
        .order_by(Match.start_time.asc())
    )
    return (await session.execute(stmt)).scalars().all()


async def get_open_matches_today(
    session,
    now: datetime.datetime = None,
    min_start_time: datetime.datetime = None,
):
    """Fetches matches in the current 06:00–06:00 UTC window that are still open for betting.

    min_start_time: when set, only matches at or after this time are returned (e.g. play-off gate).
    """
    if now is None:
        now = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(minutes=5)
    # Rolling 06:00→06:00 UTC window: before today's 06:00 we're still in yesterday's window.
    today_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)
    window_start = (
        today_6am if now >= today_6am else today_6am - datetime.timedelta(days=1)
    )
    window_end = window_start + datetime.timedelta(days=1)
    effective_start = (
        max(window_start, min_start_time) if min_start_time else window_start
    )
    stmt = (
        select(Match)
        .where(
            Match.start_time >= effective_start,
            Match.start_time < window_end,
            Match.status == "NS",
            Match.start_time > cutoff,
            Match.title != "None vs None",
        )
        .order_by(Match.start_time.asc())
    )
    return (await session.execute(stmt)).scalars().all()


async def get_upcoming_matches(session, limit=5, now: datetime.datetime = None):
    """Fetches upcoming matches."""
    if now is None:
        now = datetime.datetime.utcnow()
    stmt = (
        select(Match)
        .where(Match.start_time > now, Match.title != "None vs None")
        .order_by(Match.start_time.asc())
        .limit(limit)
    )
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


async def get_leaderboard(session, competition: str = None):
    """Fetches leaderboard rankings, optionally filtered to a single competition."""
    stmt = (
        select(
            User.display_name,
            User.username,
            User.id,
            func.sum(Bet.points_earned).label("total"),
        )
        .join(Bet)
        .join(Match, Bet.match_id == Match.id)
    )
    if competition:
        stmt = stmt.where(Match.competition == competition)
    stmt = stmt.group_by(User.id).order_by(desc("total"))
    return (await session.execute(stmt)).all()
