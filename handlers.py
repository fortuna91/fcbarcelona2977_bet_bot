import re
import datetime
import os
import logging
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, CommandObject
from sqlalchemy import select, func, desc, delete
from sqlalchemy.orm import selectinload
from models import User, Match, Bet
from database import AsyncSessionLocal

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
logger = logging.getLogger(__name__)

@router.message(CommandStart())
async def start_cmd(message: types.Message):
    logger.info(f"User {message.from_user.id} started the bot.")
    async with AsyncSessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        if not user:
            user = User(id=message.from_user.id, username=message.from_user.username)
            session.add(user)
            await session.commit()
            logger.info(f"New user registered: {message.from_user.id} (@{message.from_user.username})")
            await message.answer("🔵🔴 Welcome to the FC Barcelona Bet Bot! You're registered. Use /help for commands.")
        else:
            await message.answer("Welcome back! Ready for the next game?")

@router.message(Command("bet"))
async def place_bet(message: types.Message, command: CommandObject):
    logger.info(f"User {message.from_user.id} is attempting to place a bet with args: {command.args}")
    if not command.args:
        return await message.answer("Usage: `/bet 2:1`", parse_mode="Markdown")

    match_score = re.search(r"(\d+)[:\-](\d+)", command.args)
    if not match_score:
        return await message.answer("❌ Invalid format. Use: `/bet 2:1`")
    
    h_score, g_score = int(match_score.group(1)), int(match_score.group(2))
    now = datetime.datetime.utcnow()

    async with AsyncSessionLocal() as session:
        # Match Day only: find the earliest match today that hasn't started
        stmt = select(Match).where(Match.status == 'NS', Match.start_time > now).order_by(Match.start_time.asc())
        next_match = (await session.execute(stmt)).scalars().first()

        if not next_match or next_match.start_time.date() != now.date():
            logger.warning(f"User {message.from_user.id} tried to bet, but no match is scheduled for today.")
            return await message.answer("❌ No Barcelona matches today. Betting is only open on match days!")

        # Upsert bet
        stmt_bet = select(Bet).where(Bet.user_id == message.from_user.id, Bet.match_id == next_match.id)
        bet = (await session.execute(stmt_bet)).scalar_one_or_none()
        
        if bet:
            bet.bet_home_score, bet.bet_guest_score = h_score, g_score
            text = f"✅ Bet updated for **{next_match.title}**: `{h_score}:{g_score}`."
            logger.info(f"User {message.from_user.id} updated bet for match {next_match.id} to {h_score}:{g_score}.")
        else:
            session.add(Bet(user_id=message.from_user.id, match_id=next_match.id, bet_home_score=h_score, bet_guest_score=g_score))
            text = f"✅ Bet placed for **{next_match.title}**: `{h_score}:{g_score}`!"
            logger.info(f"User {message.from_user.id} placed new bet for match {next_match.id}: {h_score}:{g_score}.")
            
        await session.commit()
        await message.answer(text, parse_mode="Markdown")

@router.message(Command("mybets"))
async def my_bets(message: types.Message):
    logger.info(f"User {message.from_user.id} requested their betting history.")
    async with AsyncSessionLocal() as session:
        stmt = select(Bet).options(selectinload(Bet.match)).where(Bet.user_id == message.from_user.id)
        bets = (await session.execute(stmt)).scalars().all()
        
        if not bets:
            return await message.answer("You haven't placed any bets yet.")
            
        response = "📊 **Your Betting History:**\n\n"
        for bet in bets:
            m = bet.match
            res = f"{m.actual_home_score}:{m.actual_guest_score}" if m.status == 'FT' else "TBD"
            response += f"🔹 {m.title}\nBet: {bet.bet_home_score}:{bet.bet_guest_score} | Result: {res} | Points: {bet.points_earned}\n\n"
            
        await message.answer(response, parse_mode="Markdown")

@router.message(Command("leaderboard"))
async def leaderboard(message: types.Message):
    logger.info(f"User {message.from_user.id} requested the leaderboard.")
    async with AsyncSessionLocal() as session:
        stmt = select(User.username, User.id, func.sum(Bet.points_earned).label("total")).join(Bet).group_by(User.id).order_by(desc("total"))
        rankings = (await session.execute(stmt)).all()
        
        response = "🏆 **Leaderboard** 🏆\n\n"
        user_rank, user_points = 0, 0
        
        for idx, row in enumerate(rankings, 1):
            if row.id == message.from_user.id:
                user_rank, user_points = idx, row.total
            name = f"@{row.username}" if row.username else f"User {row.id}"
            response += f"{idx}. {name} — {row.total} pts\n"
            
        header = f"🎖 You are currently in **#{user_rank} place** with **{user_points} points**!\n\n" if user_rank else ""
        await message.answer(header + response, parse_mode="Markdown")

@router.message(Command("deleteme"))
async def delete_me(message: types.Message):
    logger.info(f"User {message.from_user.id} requested account deletion.")
    async with AsyncSessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        if user:
            await session.delete(user)
            await session.commit()
            logger.warning(f"User {message.from_user.id} has deleted their account.")
            await message.answer("❌ Your account and all bet history have been deleted.")
        else:
            await message.answer("Account not found.")

@router.message(Command("reset_all_scores"))
async def reset_scores(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        logger.warning(f"User {message.from_user.id} attempted to reset all scores but is not an admin.")
        return await message.answer("🚫 Admin only.")
    
    logger.warning(f"ADMIN {message.from_user.id} IS RESETTING ALL SCORES.")
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Bet))
        await session.commit()
        await message.answer("⚠️ All user scores have been reset.")
