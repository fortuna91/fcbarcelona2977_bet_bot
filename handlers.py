import re
import datetime
import os
import logging
import json
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, CommandObject
from sqlalchemy import select, func, desc, delete
from sqlalchemy.orm import selectinload
from models import User, Match, Bet
from database import AsyncSessionLocal
from scheduler import sync_matches

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
            await message.answer("🔵🔴 Добро пожаловать в FC Barcelona Bet Bot! Вы зарегистрированы. Используйте /help для просмотра команд.")
        else:
            await message.answer("С возвращением! Готовы к следующей игре?")

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    logger.info(f"User {message.from_user.id} requested help.")
    help_text = (
        "📖 **FC Barcelona Bet Bot - Команды**\n\n"
        "🔵 `/bet H:G` — Сделать или обновить ставку на сегодняшний матч (например, `/bet 2:1`).\n"
        "📅 `/games` — Посмотреть ближайшие 5 матчей Барселоны.\n"
        "🔴 `/mybets` — Посмотреть историю ставок и очки.\n"
        "🏆 `/leaderboard` — Посмотреть таблицу лидеров.\n"
        "❌ `/deleteme` — Удалить аккаунт и всю историю.\n"
        "❓ `/help` — Показать это сообщение.\n\n"
        "⚽ *Примечание: Ставки принимаются только в дни матчей до начала игры!*"
    )
    await message.answer(help_text, parse_mode="Markdown")

@router.message(Command("games"))
async def games_cmd(message: types.Message):
    logger.info(f"User {message.from_user.id} requested upcoming games.")
    now = datetime.datetime.utcnow()

    async with AsyncSessionLocal() as session:
        # Fetch the next 5 games directly from the database
        stmt = select(Match).where(Match.start_time > now).order_by(Match.start_time.asc()).limit(5)
        db_matches = (await session.execute(stmt)).scalars().all()

        if not db_matches:
            logger.info("No future matches found in DB. Forcing API sync...")
            await sync_matches()
            db_matches = (await session.execute(stmt)).scalars().all()

    if not db_matches:
        return await message.answer("К сожалению, информации о ближайших матчах пока нет.")

    response = "📅 **Ближайшие 5 матчей Барселоны:**\n\n"
    for match_obj in db_matches:
        # Format: Day.Month.Year Hour:Minute
        date_str = match_obj.start_time.strftime("%d.%m.%Y %H:%M")
        response += f"⚽ {match_obj.title}\n⏰ {date_str} (UTC)\n\n"

    await message.answer(response, parse_mode="Markdown")


@router.message(Command("bet"))
async def place_bet(message: types.Message, command: CommandObject):
    logger.info(f"User {message.from_user.id} is attempting to place a bet with args: {command.args}")
    if not command.args:
        return await message.answer("Использование: `/bet 2:1`", parse_mode="Markdown")

    match_score = re.search(r"(\d+)[:\-](\d+)", command.args)
    if not match_score:
        return await message.answer("❌ Неверный формат. Используйте: `/bet 2:1`")
    
    h_score, g_score = int(match_score.group(1)), int(match_score.group(2))
    now = datetime.datetime.utcnow()

    async with AsyncSessionLocal() as session:
        stmt = select(Match).where(Match.status == 'NS', Match.start_time > now).order_by(Match.start_time.asc())
        match_obj = (await session.execute(stmt)).scalars().first()

        if not match_obj or match_obj.start_time.date() != now.date():
            logger.warning(f"User {message.from_user.id} tried to bet, but no match is scheduled for today.")
            return await message.answer("❌ Сегодня нет матчей Барселоны. Ставки открыты только в дни матчей!")

        stmt_bet = select(Bet).where(Bet.user_id == message.from_user.id, Bet.match_id == match_obj.id)
        bet = (await session.execute(stmt_bet)).scalar_one_or_none()
        
        if bet:
            bet.bet_home_score, bet.bet_guest_score = h_score, g_score
            text = f"✅ Ставка обновлена на матч **{match_obj.title}**: `{h_score}:{g_score}`."
            logger.info(f"User {message.from_user.id} updated bet for match {match_obj.id} to {h_score}:{g_score}.")
        else:
            session.add(Bet(user_id=message.from_user.id, match_id=match_obj.id, bet_home_score=h_score, bet_guest_score=g_score))
            text = f"✅ Ставка принята на матч **{match_obj.title}**: `{h_score}:{g_score}`!"
            logger.info(f"User {message.from_user.id} placed new bet for match {match_obj.id}: {h_score}:{g_score}.")
            
        await session.commit()
        await message.answer(text, parse_mode="Markdown")

@router.message(Command("mybets"))
async def my_bets(message: types.Message):
    logger.info(f"User {message.from_user.id} requested their betting history.")
    async with AsyncSessionLocal() as session:
        stmt = select(Bet).options(selectinload(Bet.match)).where(Bet.user_id == message.from_user.id)
        bets = (await session.execute(stmt)).scalars().all()
        
        if not bets:
            return await message.answer("Вы еще не сделали ни одной ставки.")
            
        response = "📊 **Ваша история ставок:**\n\n"
        for bet in bets:
            m = bet.match
            res = f"{m.actual_home_score}:{m.actual_guest_score}" if m.status == 'FT' else "Ожидается"
            response += f"🔹 {m.title}\nСтавка: {bet.bet_home_score}:{bet.bet_guest_score} | Результат: {res} | Очки: {bet.points_earned}\n\n"
            
        await message.answer(response, parse_mode="Markdown")

@router.message(Command("leaderboard"))
async def leaderboard(message: types.Message):
    logger.info(f"User {message.from_user.id} requested the leaderboard.")
    async with AsyncSessionLocal() as session:
        stmt = select(User.username, User.id, func.sum(Bet.points_earned).label("total")).join(Bet).group_by(User.id).order_by(desc("total"))
        rankings = (await session.execute(stmt)).all()
        
        response = "🏆 **Таблица лидеров** 🏆\n\n"
        user_rank, user_points = 0, 0
        
        for idx, row in enumerate(rankings, 1):
            if row.id == message.from_user.id:
                user_rank, user_points = idx, row.total
            name = f"@{row.username}" if row.username else f"Пользователь {row.id}"
            response += f"{idx}. {name} — {row.total} очк.\n"
            
        header = f"🎖 Вы сейчас на **{user_rank} месте** с **{user_points} очками**!\n\n" if user_rank else ""
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
            await message.answer("❌ Ваш аккаунт и вся история ставок удалены.")
        else:
            await message.answer("Аккаунт не найден.")

@router.message(Command("reset_all_scores"))
async def reset_scores(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        logger.warning(f"User {message.from_user.id} attempted to reset all scores but is not an admin.")
        return await message.answer("🚫 Только для администратора.")
    
    logger.warning(f"ADMIN {message.from_user.id} IS RESETTING ALL SCORES.")
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Bet))
        await session.commit()
        await message.answer("⚠️ Все очки пользователей сброшены.")
