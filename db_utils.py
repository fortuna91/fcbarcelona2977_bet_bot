import datetime
import pytz
from sqlalchemy import select, func, desc
from models import User, Match, Bet
from flags import EMPTY_TITLES, TBD_TEAM

MSK_TZ = pytz.timezone("Europe/Moscow")

# A match is open for betting starting this long before kickoff. 24h means a match
# can always be predicted the previous evening — including 4am МСК (USA) games.
BETTING_HORIZON = datetime.timedelta(hours=24)


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


async def get_open_matches(
    session,
    now: datetime.datetime = None,
    min_start_time: datetime.datetime = None,
):
    """Fetches matches open for betting: kicking off within the next BETTING_HORIZON.

    A match is bettable from 24h before kickoff until 5 minutes before it, so an
    early-morning (e.g. 4am МСК) match can still be predicted the previous evening.
    min_start_time: when set, only matches at or after this time are returned (e.g. play-off gate).
    """
    if now is None:
        now = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(minutes=5)
    horizon_end = now + BETTING_HORIZON
    conditions = [
        Match.start_time > cutoff,
        Match.start_time <= horizon_end,
        Match.status == "NS",
        # Both teams must be known — never offer a bet on an undecided opponent
        # (the «Ожидается» placeholder, or a legacy "None" not yet re-synced).
        Match.title.not_like(f"%{TBD_TEAM}%"),
        Match.title.not_like("%None%"),
    ]
    if min_start_time:
        conditions.append(Match.start_time >= min_start_time)
    stmt = select(Match).where(*conditions).order_by(Match.start_time.asc())
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
