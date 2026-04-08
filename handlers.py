import re
import datetime
import os
import logging
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select, func, desc, delete
from sqlalchemy.orm import selectinload
from models import User, Match, Bet
from database import AsyncSessionLocal
from scheduler import sync_matches
import db_utils


# FSM States
class BettingStates(StatesGroup):
    waiting_for_score = State()


router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
logger = logging.getLogger(__name__)

# Flexible regex for scores: 2:1, 2 1, 2 : 1, 2-1, etc.
SCORE_REGEX = r"(\d+)\s*[:\-\s]\s*(\d+)"


def is_betting_allowed(start_time: datetime.datetime, now: datetime.datetime = None) -> bool:
    """Checks if betting is allowed (more than 5 minutes before start)."""
    if now is None:
        now = datetime.datetime.utcnow()
    return (start_time - now) > datetime.timedelta(minutes=5)


def parse_score(text: str):
    """Parses score from text using regex."""
    match = re.search(SCORE_REGEX, text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def get_bet_confirmation_keyboard(match_id, h, g):
    """Returns an inline keyboard for bet confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_bet_change:{match_id}:{h}:{g}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="cancel_bet_change")
        ]
    ])


def format_match_list(matches):
    """Formats a list of matches for display."""
    response = "📅 **Ближайшие 5 матчей Барселоны:**\n\n"
    for match_obj in matches:
        date_str = match_obj.start_time.strftime("%d.%m.%Y %H:%M")
        response += f"⚽ {match_obj.title}\n⏰ {date_str} (UTC)\n\n"
    return response


def get_too_late_msg(match_obj: Match, existing_bet: Bet = None) -> str:
    """Returns a 'too late' message for the given match and optional existing bet."""
    if existing_bet:
        h, g = existing_bet.bet_home_score, existing_bet.bet_guest_score
        return (f"❌ Слишком поздно менять прогноз на матч **{match_obj.title}**! "
                f"Матч начинается менее чем через 5 минут или уже идет. "
                f"Твой прогноз: `{h}:{g}`.")
    return (f"❌ Слишком поздно для прогноза на матч **{match_obj.title}**! "
            f"Матч начинается менее чем через 5 минут или уже идет.")


@router.message(CommandStart())
async def start_cmd(message: types.Message):
    logger.info(f"User {message.from_user.id} started the bot.")
    full_name = message.from_user.full_name
    async with AsyncSessionLocal() as session:
        user = await db_utils.get_user(session, message.from_user.id)
        if not user:
            user = User(
                id=message.from_user.id, 
                username=message.from_user.username,
                display_name=full_name
            )
            session.add(user)
            await session.commit()
            logger.info(f"New user registered: {message.from_user.id} ({full_name})")
            await message.answer(f"🔵🔴 Добро пожаловать, {full_name}, в Club2977 Score Bot! Тут мы пытаемся угадать счет матчей Барселоны! Используйте /help для просмотра команд.")
        else:
            # Update name if changed
            user.display_name = full_name
            await session.commit()
            await message.answer(f"С возвращением, {full_name}! Готовы к следующей игре?")


@router.message(Command("help"))
async def help_cmd(message: types.Message):
    logger.info(f"User {message.from_user.id} requested help.")
    help_text = (
        "📖 **FC Barcelona Bet Bot - Команды**\n\n"
        "/bet H:G — Сделать или обновить прогноз на сегодняшний матч (например, `/bet 2:1` or just `/bet`).\n"
        "/games — Посмотреть ближайшие 5 матчей Барселоны.\n"
        "/mybets — Посмотреть историю прогнозов и очки.\n"
        "/leaderboard — Посмотреть таблицу лидеров.\n"
        "/deleteme — Удалить аккаунт и всю историю.\n"
        "/help — Показать это сообщение.\n\n"
        "⚽ *Примечание: Прогнозы принимаются только в дни матчей до начала игры!*"
    )
    await message.answer(help_text, parse_mode="Markdown")


@router.message(Command("games"))
async def games_cmd(message: types.Message):
    logger.info(f"User {message.from_user.id} requested upcoming games.")
    now = datetime.datetime.utcnow()

    async with AsyncSessionLocal() as session:
        db_matches = await db_utils.get_upcoming_matches(session, limit=5, now=now)

        if not db_matches:
            logger.info("No future matches found in DB. Forcing API sync...")
            await sync_matches()
            db_matches = await db_utils.get_upcoming_matches(session, limit=5, now=now)

    if not db_matches:
        return await message.answer("К сожалению, информации о ближайших матчах пока нет.")

    await message.answer(format_match_list(db_matches), parse_mode="Markdown")


@router.message(Command("bet"))
async def place_bet(message: types.Message, command: CommandObject, state: FSMContext):
    logger.info(f"User {message.from_user.id} called /bet with args: {command.args}")
    now = datetime.datetime.utcnow()

    async with AsyncSessionLocal() as session:
        match_obj = await db_utils.get_next_match(session, now)

        # CASE A: No match today
        if not match_obj or match_obj.start_time.date() != now.date():
            next_game = await db_utils.get_next_match(session, now)
            
            msg = "❌ Сегодня нет матчей Барселоны. Прогнозы принимаются только в дни матчей!"
            if next_game:
                date_str = next_game.start_time.strftime("%d.%m.%Y %H:%M")
                msg += f"\n\n📅 Следующая игра:\n**{next_game.title}**\n⏰ {date_str} (UTC)"
            
            return await message.answer(msg, parse_mode="Markdown")

        # CASE B: Match exists today
        if not is_betting_allowed(match_obj.start_time, now):
            existing_bet = await db_utils.get_user_bet(session, message.from_user.id, match_obj.id)
            msg = get_too_late_msg(match_obj, existing_bet)
            return await message.answer(msg, parse_mode="Markdown")

        if command.args:
            score = parse_score(command.args)
            if not score:
                return await message.answer("❌ Неверный формат. Используйте: `2:1`, `2 1` или `2-1`.")
            
            h_score, g_score = score
            
            # Check for existing bet
            existing_bet = await db_utils.get_user_bet(session, message.from_user.id, match_obj.id)
            
            if existing_bet:
                kb = get_bet_confirmation_keyboard(match_obj.id, h_score, g_score)
                msg = (f"⚠️ У тебя уже сделан прогноз на матч **{match_obj.title}**.\n"
                       f"Твой прогноз: `{existing_bet.bet_home_score}:{existing_bet.bet_guest_score}`.\n\n"
                       f"Хочешь изменить его на `{h_score}:{g_score}`?")
                return await message.answer(msg, reply_markup=kb, parse_mode="Markdown")
            
            await save_bet(message, message.from_user.id, session, match_obj, h_score, g_score)
        else:
            await state.set_state(BettingStates.waiting_for_score)
            await state.update_data(match_id=match_obj.id)
            await message.answer(
                f"⚽ Сегодня игра: **{match_obj.title}**\n"
                f"⏰ Начало: {match_obj.start_time.strftime('%H:%M')} (UTC)\n\n"
                f"Пришли свой прогноз (например, `2:1` или `2 1`):",
                parse_mode="Markdown"
            )


@router.message(BettingStates.waiting_for_score)
async def process_bet_score(message: types.Message, state: FSMContext):
    score = parse_score(message.text)
    if not score:
        return await message.answer("❌ Неверный формат. Пожалуйста, введите счет в формате `2:1` или `2 1`.")

    h_score, g_score = score
    data = await state.get_data()
    match_id = data.get("match_id")

    async with AsyncSessionLocal() as session:
        match_obj = await session.get(Match, match_id)
        if not match_obj or match_obj.status == 'FT' or not is_betting_allowed(match_obj.start_time):
            await state.clear()
            if match_obj:
                existing_bet = await db_utils.get_user_bet(session, message.from_user.id, match_obj.id)
                msg = get_too_late_msg(match_obj, existing_bet)
            else:
                msg = "❌ Извини, время для прогноза на этот матч истекло."
            
            return await message.answer(msg, parse_mode="Markdown")

        # Check if user already has a bet for this match
        existing_bet = await db_utils.get_user_bet(session, message.from_user.id, match_obj.id)

        if existing_bet:
            kb = get_bet_confirmation_keyboard(match_obj.id, h_score, g_score)
            msg = (f"⚠️ У тебя уже сделан прогноз на этот матч **{match_obj.title}**.\n"
                   f"Твой прогноз: `{existing_bet.bet_home_score}:{existing_bet.bet_guest_score}`.\n\n"
                   f"Хочешь изменить его на `{h_score}:{g_score}`?")
            await state.clear()
            return await message.answer(msg, reply_markup=kb, parse_mode="Markdown")

        await save_bet(message, message.from_user.id, session, match_obj, h_score, g_score)
    
    await state.clear()


@router.callback_query(F.data.startswith("confirm_bet_change:"))
async def confirm_bet_change(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    match_id = int(parts[1])
    h_score = int(parts[2])
    g_score = int(parts[3])
    
    async with AsyncSessionLocal() as session:
        match_obj = await session.get(Match, match_id)
        if not match_obj or not is_betting_allowed(match_obj.start_time):
            await callback.message.edit_text("❌ Извини, время для изменения прогноза истекло.", reply_markup=None)
            return await callback.answer()
            
        await save_bet(callback.message, callback.from_user.id, session, match_obj, h_score, g_score)
    
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "cancel_bet_change")
async def cancel_bet_change(callback: CallbackQuery):
    await callback.message.edit_text("ОК, оставляем как есть.", reply_markup=None)
    await callback.answer()


async def save_bet(message: types.Message, user_id: int, session, match_obj, h_score, g_score):
    stmt_bet = select(Bet).where(Bet.user_id == user_id, Bet.match_id == match_obj.id)
    bet = (await session.execute(stmt_bet)).scalar_one_or_none()
    
    if bet:
        bet.bet_home_score, bet.bet_guest_score = h_score, g_score
        text = f"✅ Прогноз обновлен на матч **{match_obj.title}**: `{h_score}:{g_score}`."
        logger.info(f"User {user_id} updated bet for match {match_obj.id} to {h_score}:{g_score}.")
    else:
        session.add(Bet(user_id=user_id, match_id=match_obj.id, bet_home_score=h_score, bet_guest_score=g_score))
        text = f"✅ Прогноз принят на матч **{match_obj.title}**: `{h_score}:{g_score}`!"
        logger.info(f"User {user_id} placed new bet for match {match_obj.id}: {h_score}:{g_score}.")
        
    await session.commit()
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("mybets"))
async def my_bets(message: types.Message):
    logger.info(f"User {message.from_user.id} requested their betting history.")
    async with AsyncSessionLocal() as session:
        stmt = select(Bet).options(selectinload(Bet.match)).where(Bet.user_id == message.from_user.id)
        bets = (await session.execute(stmt)).scalars().all()
        
        if not bets:
            return await message.answer("У тебя еще нет ни одного прогноза.")
            
        response = "📊 **Твоя история прогнозов:**\n\n"
        for bet in bets:
            m = bet.match
            res = f"{m.actual_home_score}:{m.actual_guest_score}" if m.status == 'FT' else "Ожидается"
            response += f"🔹 {m.title}\nПрогноз: {bet.bet_home_score}:{bet.bet_guest_score} | Результат: {res} | Очки: {bet.points_earned}\n\n"
            
        await message.answer(response, parse_mode="Markdown")


@router.message(Command("leaderboard"))
async def leaderboard(message: types.Message):
    logger.info(f"User {message.from_user.id} requested the leaderboard.")
    async with AsyncSessionLocal() as session:
        rankings = await db_utils.get_leaderboard(session)
        
        response = "🏆 **Таблица лидеров** 🏆\n\n"
        user_rank, user_points = 0, 0
        
        for idx, row in enumerate(rankings, 1):
            if row.id == message.from_user.id:
                user_rank, user_points = idx, row.total
            name = row.display_name or (f"@{row.username}" if row.username else f"User {row.id}")
            response += f"{idx}. {name} — {row.total} очк.\n"
            
        header = f"🎖 Ты сейчас на **{user_rank} месте** с **{user_points} очками**!\n\n" if user_rank else ""
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
            await message.answer("❌ Твой аккаунт и вся история прогнозов удалены.")
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
