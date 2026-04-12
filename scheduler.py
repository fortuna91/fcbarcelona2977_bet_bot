import datetime
import logging
import pytz
from sqlalchemy import select, func
from aiogram import Bot
from football_api import FootballAPI
from models import Match, User, Bet
from points_calculator import calculate_points
from database import AsyncSessionLocal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import db_utils

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone='UTC')

MSK_TZ = pytz.timezone("Europe/Moscow")


def format_match_time_msk(dt: datetime.datetime) -> str:
    """Converts UTC datetime to Moscow time and formats it."""
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    msk_dt = dt.astimezone(MSK_TZ)
    return msk_dt.strftime("%H:%M МСК")


async def notify_users(bot: Bot, users, text: str):
    """Helper to send the same message to multiple users."""
    for user in users:
        try:
            await bot.send_message(user.id, text)
        except Exception as e:
            logger.debug(f"Could not send notification to {user.id}: {e}")


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


async def check_results_and_notify(bot: Bot, match_id: int):
    logger.info(f"Checking results for match ID: {match_id}...")
    api = FootballAPI()
    async with AsyncSessionLocal() as session:
        match_obj = await session.get(Match, match_id)
        if not match_obj or match_obj.status == 'FT':
            logger.info(f"Match {match_id} already processed or not found. Removing job.")
            try:
                scheduler.remove_job(f"check_{match_id}")
            except:
                pass
            return

        data = await api.get_fixture_by_id(match_id)
        
        if data and data['status'] == 'FINISHED':
            ah = data['score']['fullTime']['home']
            ag = data['score']['fullTime']['away']
            logger.info(f"Match {match_id} finished. Score: {ah}-{ag}")
            match_obj.actual_home_score, match_obj.actual_guest_score, match_obj.status = ah, ag, 'FT'
            
            stmt_bets = select(Bet).where(Bet.match_id == match_obj.id)
            bets = (await session.execute(stmt_bets)).scalars().all()
            logger.info(f"Calculating points for {len(bets)} bets on match {match_obj.id}.")
            
            for bet in bets:
                bet.points_earned = calculate_points(bet.bet_home_score, bet.bet_guest_score, ah, ag)
            
            await session.flush()
            for bet in bets:
                total_stmt = select(func.sum(Bet.points_earned)).where(Bet.user_id == bet.user_id)
                total = (await session.execute(total_stmt)).scalar() or 0
                
                # Simple rank calculation: count users with more points
                rank_stmt = select(func.count(User.id)).select_from(User).join(Bet).group_by(User.id).having(func.sum(Bet.points_earned) > total)
                rank = len((await session.execute(rank_stmt)).all()) + 1
                
                try:
                    await bot.send_message(bet.user_id, f"🏁 Матч окончен!\n{match_obj.title}: {ah}-{ag}\nОчки: +{bet.points_earned}\nВсего: {total}\nМесто в рейтинге: #{rank}")
                except Exception as e:
                    logger.warning(f"Failed to send notification to user {bet.user_id}: {e}")
            
            await session.commit()
            logger.info(f"Results processed for match {match_id}. Removing job.")
            try:
                scheduler.remove_job(f"check_{match_id}")
            except:
                pass
        else:
            logger.info(f"Match {match_id} is still in progress or not finished yet.")


async def schedule_match_jobs(bot: Bot, match_obj: Match):
    """Schedules result checking and hourly reminders for a match."""
    now = datetime.datetime.utcnow()
    
    # 1. Result checking (starts 1h 50m after kickoff)
    start_poll = match_obj.start_time + datetime.timedelta(minutes=110)
    # If the match has already started long ago, start polling almost immediately
    if start_poll < now:
        start_poll = now + datetime.timedelta(seconds=10)

    scheduler.add_job(
        check_results_and_notify,
        'interval',
        minutes=5,
        start_date=start_poll,
        args=[bot, match_obj.id],
        id=f"check_{match_obj.id}",
        replace_existing=True
    )
    logger.info(f"Scheduled result checking for match {match_obj.id} starting at {start_poll}")

    # 2. Hourly reminder (1 hour before kickoff)
    reminder_time = match_obj.start_time - datetime.timedelta(hours=1)
    # Only schedule if it's still in the future
    if reminder_time > now:
        scheduler.add_job(
            hourly_bet_reminder,
            'date',
            run_date=reminder_time,
            args=[bot, match_obj.id],
            id=f"hourly_{match_obj.id}",
            replace_existing=True
        )
        logger.info(f"Scheduled hourly reminder for match {match_obj.id} at {reminder_time}")
    else:
        logger.debug(f"Hourly reminder for match {match_obj.id} skipped (time passed).")


async def check_upcoming_jobs(bot: Bot):
    """Checks database for unfinished matches and re-schedules jobs on startup."""
    logger.info("Checking for upcoming/in-progress matches to re-schedule jobs...")
    async with AsyncSessionLocal() as session:
        # Find matches that are not yet finished
        stmt = select(Match).where(Match.status == 'NS')
        matches = (await session.execute(stmt)).scalars().all()
        
        for match_obj in matches:
            # Re-schedule jobs for matches starting today or already in progress
            now = datetime.datetime.utcnow()
            if match_obj.start_time < now + datetime.timedelta(hours=24):
                await schedule_match_jobs(bot, match_obj)


async def daily_match_reminder(bot: Bot):
    """Sends a reminder at 8 AM if there is a match today to users who haven't bet."""
    logger.info("Checking for daily match reminders...")
    now = datetime.datetime.utcnow()
    async with AsyncSessionLocal() as session:
        # Find match for today
        stmt = select(Match).where(func.date(Match.start_time) == now.date())
        match_obj = (await session.execute(stmt)).scalars().first()

        if match_obj:
            logger.info(f"Match found today: {match_obj.title}. Identifying users who haven't bet.")
            # Find users who haven't placed a bet for this match
            users = await db_utils.get_users_without_bet(session, match_obj.id)
            
            time_str = format_match_time_msk(match_obj.start_time)
            msg = f"⚽ День матча!\nСегодня в {time_str} нас ждет: {match_obj.title}.\nНе забудь сделать прогноз с помощью /bet"
            await notify_users(bot, users, msg)

            # Schedule result checking and hourly reminder
            await schedule_match_jobs(bot, match_obj)


async def hourly_bet_reminder(bot: Bot, match_id: int):
    """Sends a reminder 1 hour before kickoff to users who haven't bet for the given match."""
    logger.info(f"Running hourly reminder for match ID: {match_id}")
    async with AsyncSessionLocal() as session:
        match_obj = await session.get(Match, match_id)
        if not match_obj or match_obj.status == 'FT':
            return

        # Find users who haven't placed a bet for this match
        users = await db_utils.get_users_without_bet(session, match_obj.id)
        
        time_str = format_match_time_msk(match_obj.start_time)
        msg = f"⏰ Последний шанс!\nВ {time_str} Барселона начинает матч {match_obj.title}.\nТы еще успеешь сделать ставку! Используй /bet прямо сейчас."
        await notify_users(bot, users, msg)


def setup_scheduler(bot: Bot):
    logger.info("Configuring scheduler jobs...")
    scheduler.add_job(sync_matches, 'cron', hour=2)
    scheduler.add_job(daily_match_reminder, 'cron', hour=6, args=[bot])
    
    # Run sync and job check on startup
    scheduler.add_job(check_upcoming_jobs, 'date', run_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=5), args=[bot])
    
    scheduler.start()
    logger.info("Scheduler started.")
