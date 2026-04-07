import datetime
import logging
from sqlalchemy import select, func
from aiogram import Bot
from football_api import FootballAPI
from models import Match, User, Bet
from points_calculator import calculate_points
from database import AsyncSessionLocal
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

async def sync_matches():
    logger.info("Starting match synchronization...")
    api = FootballAPI()
    try:
        data = await api.get_fixtures()
        logger.info(f"Fetched {len(data)} fixtures from API.")
        async with AsyncSessionLocal() as session:
            for item in data:
                f = item['fixture']
                dt_str = f['date'].replace('Z', '+00:00')
                dt = datetime.datetime.fromisoformat(dt_str).replace(tzinfo=None)
                title = f"{item['teams']['home']['name']} vs {item['teams']['away']['name']}"
                match = await session.get(Match, f['id'])
                if not match:
                    session.add(Match(id=f['id'], title=title, start_time=dt, status=f['status']['short']))
                else:
                    match.status = f['status']['short']
                    match.start_time = dt
            await session.commit()
            logger.info("Match synchronization completed successfully.")
    except Exception as e:
        logger.error(f"Error during match synchronization: {e}", exc_info=True)

async def check_results_and_notify(bot: Bot):
    logger.info("Checking for finished matches and updating scores...")
    api = FootballAPI()
    async with AsyncSessionLocal() as session:
        now = datetime.datetime.utcnow()
        stmt = select(Match).where(Match.status != 'FT', Match.start_time < now)
        pending = (await session.execute(stmt)).scalars().all()

        if not pending:
            logger.info("No pending matches to check.")
            return

        for match in pending:
            logger.info(f"Checking status for match: {match.title} (ID: {match.id})")
            data = await api.get_fixture_by_id(match.id)
            if data and data['fixture']['status']['short'] == 'FT':
                ah, ag = data['goals']['home'], data['goals']['away']
                logger.info(f"Match {match.id} finished. Score: {ah}-{ag}")
                match.actual_home_score, match.actual_guest_score, match.status = ah, ag, 'FT'
                
                stmt_bets = select(Bet).where(Bet.match_id == match.id)
                bets = (await session.execute(stmt_bets)).scalars().all()
                logger.info(f"Calculating points for {len(bets)} bets on match {match.id}.")
                
                for bet in bets:
                    bet.points_earned = calculate_points(bet.bet_home_score, bet.bet_guest_score, ah, ag)
                
                await session.flush()
                for bet in bets:
                    total = (await session.execute(select(func.sum(Bet.points_earned)).where(Bet.user_id == bet.user_id))).scalar()
                    rank_stmt = select(func.count(User.id)).select_from(User).join(Bet).group_by(User.id).having(func.sum(Bet.points_earned) > total)
                    rank = len((await session.execute(rank_stmt)).all()) + 1
                    try:
                        await bot.send_message(bet.user_id, f"🏁 Match Finished!\n{match.title}: {ah}-{ag}\nPoints: +{bet.points_earned}\nTotal: {total}\nRank: #{rank}")
                    except Exception as e:
                        logger.warning(f"Failed to send notification to user {bet.user_id}: {e}")
        await session.commit()

async def daily_match_reminder(bot: Bot):
    """Sends a reminder at 8 AM if there is a match today."""
    logger.info("Checking for daily match reminders...")
    now = datetime.datetime.utcnow()
    async with AsyncSessionLocal() as session:
        stmt = select(Match).where(func.date(Match.start_time) == now.date())
        match = (await session.execute(stmt)).scalars().first()
        if match:
            logger.info(f"Match found today: {match.title}. Sending reminders...")
            users = (await session.execute(select(User))).scalars().all()
            for user in users:
                try:
                    await bot.send_message(user.id, f"⚽ **Match Day!**\nFC Barcelona plays today: *{match.title}*.\nDon't forget to place your bet using /bet!")
                except Exception as e:
                    logger.debug(f"Could not send daily reminder to {user.id}: {e}")

async def hourly_bet_reminder(bot: Bot):
    """Sends a reminder 1 hour before kickoff to users who haven't bet."""
    logger.info("Checking for hourly bet reminders...")
    now = datetime.datetime.utcnow()
    one_hour_later = now + datetime.timedelta(hours=1)
    async with AsyncSessionLocal() as session:
        # Find matches starting in ~1 hour
        stmt = select(Match).where(Match.start_time > now, Match.start_time <= one_hour_later)
        match = (await session.execute(stmt)).scalars().first()
        
        if match:
            logger.info(f"Kickoff in ~1 hour for: {match.title}. Identifying users who haven't bet.")
            # Find users who haven't placed a bet for this match
            subquery = select(Bet.user_id).where(Bet.match_id == match.id)
            stmt_users = select(User).where(User.id.not_in(subquery))
            users = (await session.execute(stmt_users)).scalars().all()
            
            for user in users:
                try:
                    await bot.send_message(user.id, f"⏰ **Final Call!**\nBarcelona kicks off in 1 hour vs *{match.title}*.\nYou haven't placed a bet yet! Use /bet now.")
                except Exception as e:
                    logger.debug(f"Could not send hourly reminder to {user.id}: {e}")

def setup_scheduler(bot: Bot):
    logger.info("Configuring scheduler jobs...")
    scheduler.add_job(sync_matches, 'cron', hour=2)
    scheduler.add_job(check_results_and_notify, 'interval', minutes=30, args=[bot])
    scheduler.add_job(daily_match_reminder, 'cron', hour=8, args=[bot])
    scheduler.add_job(hourly_bet_reminder, 'interval', minutes=10, args=[bot])
    scheduler.start()
    logger.info("Scheduler started.")
