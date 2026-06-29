import datetime
import pytz
from sqlalchemy import select, func, desc
from models import User, Match, Bet
from flags import EMPTY_TITLES

MSK_TZ = pytz.timezone("Europe/Moscow")


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
            Match.status == "NS",
            Match.start_time > now,
            Match.title.not_in(EMPTY_TITLES),
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
    """Fetches matches on the current Moscow calendar day that are still open for betting.

    The betting day is the Moscow-time calendar day (matches are displayed in МСК),
    running from 00:00 МСК to 00:00 МСК the next day.
    min_start_time: when set, only matches at or after this time are returned (e.g. play-off gate).
    """
    if now is None:
        now = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(minutes=5)
    # Betting day = Moscow calendar day. start_time is naive UTC, so resolve the
    # MSK midnight bounds and convert them back to naive UTC for comparison.
    now_msk = pytz.utc.localize(now).astimezone(MSK_TZ)
    msk_midnight = now_msk.replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = msk_midnight.astimezone(pytz.utc).replace(tzinfo=None)
    window_end = (
        (msk_midnight + datetime.timedelta(days=1))
        .astimezone(pytz.utc)
        .replace(tzinfo=None)
    )
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
            Match.title.not_in(EMPTY_TITLES),
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
        .where(Match.start_time > now, Match.title.not_in(EMPTY_TITLES))
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
