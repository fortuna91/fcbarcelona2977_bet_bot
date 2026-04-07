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
    logger.info("Starting match synchronization (football-data.org)...")
    api = FootballAPI()
    try:
        data = await api.get_fixtures()
        logger.info(f"Fetched {len(data)} fixtures from API.")
        async with AsyncSessionLocal() as session:
            for item in data:
                f_id = item['id']
                # football-data.org date format: "2026-03-15T20:00:00Z"
                dt_str = item['utcDate'].replace('Z', '+00:00')
                dt = datetime.datetime.fromisoformat(dt_str).replace(tzinfo=None)
                
                home_name = item['homeTeam']['shortName'] or item['homeTeam']['name']
                away_name = item['awayTeam']['shortName'] or item['awayTeam']['name']
                title = f"{home_name} vs {away_name}"
                
                # football-data.org status: FINISHED, SCHEDULED, TIMED, IN_PLAY, PAUSED, POSTPONED, CANCELLED
                # Map them to simplified statuses: FT or NS
                raw_status = item['status']
                status = 'FT' if raw_status == 'FINISHED' else 'NS'
                
                match_obj = await session.get(Match, f_id)
                if not match_obj:
                    match_obj = Match(id=f_id, title=title, start_time=dt, status=status)
                    session.add(match_obj)
                else:
                    match_obj.status = status
                    match_obj.start_time = dt
                    
                # If finished, update actual scores too
                if status == 'FT':
                    match_obj.actual_home_score = item['score']['fullTime']['home']
                    match_obj.actual_guest_score = item['score']['fullTime']['away']
                    
            await session.commit()
            logger.info("Match synchronization completed successfully.")
    except Exception as e:
        logger.error(f"Error during match synchronization: {e}", exc_info=True)

async def check_results_and_notify(bot: Bot):
    logger.info("Checking for finished matches and updating scores...")
    api = FootballAPI()
    async with AsyncSessionLocal() as session:
        now = datetime.datetime.utcnow()
        # Find matches that are not 'FT' but should have finished by now (e.g., 2.5 hours after start)
        cutoff = now - datetime.timedelta(hours=2, minutes=30)
        stmt = select(Match).where(Match.status != 'FT', Match.start_time < cutoff)
        pending = (await session.execute(stmt)).scalars().all()

        if not pending:
            logger.info("No pending matches to check.")
            return

        for match_obj in pending:
            logger.info(f"Checking status for match: {match_obj.title} (ID: {match_obj.id})")
            data = await api.get_fixture_by_id(match_obj.id)
            
            if data and data['status'] == 'FINISHED':
                ah = data['score']['fullTime']['home']
                ag = data['score']['fullTime']['away']
                logger.info(f"Match {match_obj.id} finished. Score: {ah}-{ag}")
                match_obj.actual_home_score, match_obj.actual_guest_score, match_obj.status = ah, ag, 'FT'
                
                stmt_bets = select(Bet).where(Bet.match_id == match_obj.id)
                bets = (await session.execute(stmt_bets)).scalars().all()
                logger.info(f"Calculating points for {len(bets)} bets on match {match_obj.id}.")
                
                for bet in bets:
                    bet.points_earned = calculate_points(bet.bet_home_score, bet.bet_guest_score, ah, ag)
                
                await session.flush()
                for bet in bets:
                    total = (await session.execute(select(func.sum(Bet.points_earned)).where(Bet.user_id == bet.user_id))).scalar()
                    rank_stmt = select(func.count(User.id)).select_from(User).join(Bet).group_by(User.id).having(func.sum(Bet.points_earned) > total)
                    rank = len((await session.execute(rank_stmt)).all()) + 1
                    try:
                        await bot.send_message(bet.user_id, f"🏁 Матч окончен!\n{match_obj.title}: {ah}-{ag}\nОчки: +{bet.points_earned}\nВсего: {total}\nМесто в рейтинге: #{rank}")
                    except Exception as e:
                        logger.warning(f"Failed to send notification to user {bet.user_id}: {e}")
        await session.commit()

async def daily_match_reminder(bot: Bot):
    """Sends a reminder at 8 AM if there is a match today."""
    logger.info("Checking for daily match reminders...")
    now = datetime.datetime.utcnow()
    async with AsyncSessionLocal() as session:
        stmt = select(Match).where(func.date(Match.start_time) == now.date())
        match_obj = (await session.execute(stmt)).scalars().first()
        if match_obj:
            logger.info(f"Match found today: {match_obj.title}. Sending reminders...")
            users = (await session.execute(select(User))).scalars().all()
            for user in users:
                try:
                    await bot.send_message(user.id, f"⚽ **День матча!**\nБарселона играет сегодня: *{match_obj.title}*.\nНе забудьте сделать ставку с помощью /bet!")
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
        match_obj = (await session.execute(stmt)).scalars().first()
        
        if match_obj:
            logger.info(f"Kickoff in ~1 hour for: {match_obj.title}. Identifying users who haven't bet.")
            # Find users who haven't placed a bet for this match
            subquery = select(Bet.user_id).where(Bet.match_id == match_obj.id)
            stmt_users = select(User).where(User.id.not_in(subquery))
            users = (await session.execute(stmt_users)).scalars().all()
            
            for user in users:
                try:
                    await bot.send_message(user.id, f"⏰ **Последний шанс!**\nБарселона начинает через час против *{match_obj.title}*.\nВы еще не сделали ставку! Используйте /bet прямо сейчас.")
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
