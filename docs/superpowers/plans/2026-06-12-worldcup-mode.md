# World Cup 2026 Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reversible `COMPETITION` env toggle that makes the bot fetch World Cup matches instead of FC Barcelona, and rework the bet flow so users can predict every match on a given day.

**Architecture:** A competition toggle at the data-source layer (`football_api.py`) swaps the fixtures endpoint; the scheduler and scoring logic already work per-match and barely change. The `/bet` flow gains an inline-keyboard match picker for days with multiple matches. Removing `COMPETITION` from `.env` restores Barça mode with no code change.

**Tech Stack:** Python 3.11, aiogram (Telegram), SQLAlchemy async, APScheduler, httpx, pytest.

---

## Reference: design spec

Full design at `docs/superpowers/specs/2026-06-12-worldcup-mode-design.md`. Key locked decisions: bet on all daily matches; env-var toggle `COMPETITION=WC`; inline-button match selection; no `COMPETITION_NAME` label; all UI stays Russian.

**Precondition:** the `FOOTBALL_API_KEY` in `.env` is currently rejected by the API (400). The code changes don't depend on it, but live end-to-end testing needs a valid free-tier key.

## File map

- `football_api.py` — Modify: add `self.competition`, add `_fixtures_url()`, use it in `get_fixtures()`.
- `db_utils.py` — Modify: add `get_matches_on_day`, add `get_open_matches_today`, remove now-unused `get_match_on_day`.
- `handlers.py` — Modify: add pure helpers `decide_bet_action` / `format_match_button_label` / `get_match_choice_keyboard` / `prompt_or_save`; rework `place_bet`; add `pick_match` callback; genericize copy.
- `scheduler.py` — Modify: rework `daily_match_reminder` for multiple matches; genericize `hourly_bet_reminder` text.
- `tests/test_football_api.py` — Create: URL-builder tests.
- `tests/test_bet_helpers.py` — Create: tests for `decide_bet_action` and `format_match_button_label`.
- `.env` — Modify (local, gitignored): add `COMPETITION=WC`.
- `CLAUDE.md` — Modify: document the `COMPETITION` env var.

> **Testing note:** Per the approved spec, only pure-logic functions get committed unit tests. The async DB queries in `db_utils.py` are verified with a one-off manual snippet (Task 2), matching the repo's convention of not committing DB-bound tests. `pytest` is NOT in `requirements.txt` — install it first: `pip install pytest`.

---

## Task 1: Competition toggle in football_api.py

**Files:**
- Modify: `football_api.py`
- Test: `tests/test_football_api.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_football_api.py`:

```python
from football_api import FootballAPI


def test_fixtures_url_team_mode(monkeypatch):
    monkeypatch.delenv("COMPETITION", raising=False)
    api = FootballAPI()
    assert api._fixtures_url() == "https://api.football-data.org/v4/teams/81/matches"


def test_fixtures_url_competition_mode(monkeypatch):
    monkeypatch.setenv("COMPETITION", "WC")
    api = FootballAPI()
    assert api._fixtures_url() == "https://api.football-data.org/v4/competitions/WC/matches"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_football_api.py -v`
Expected: FAIL — `AttributeError: 'FootballAPI' object has no attribute '_fixtures_url'`.

- [ ] **Step 3: Implement the toggle**

In `football_api.py`, add the competition attribute in `__init__` (after `self.team_id = 81`):

```python
        self.team_id = 81 # FC Barcelona ID in football-data.org
        # When set (e.g. "WC"), fetch a whole competition instead of one team's matches.
        self.competition = os.getenv("COMPETITION")
```

Add this method directly above `get_fixtures`:

```python
    def _fixtures_url(self) -> str:
        """Builds the fixtures URL: a competition's matches if COMPETITION is set, else the team's."""
        if self.competition:
            return f"{self.base_url}/competitions/{self.competition}/matches"
        return f"{self.base_url}/teams/{self.team_id}/matches"
```

Change the first two lines of `get_fixtures` from:

```python
        """Fetch all FC Barcelona matches for the current season."""
        url = f"{self.base_url}/teams/{self.team_id}/matches"
        logger.info(f"Requesting matches for team {self.team_id} from football-data.org...")
```

to:

```python
        """Fetch all matches for the configured competition (or FC Barcelona by default)."""
        url = self._fixtures_url()
        logger.info(f"Requesting fixtures from {url}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_football_api.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add football_api.py tests/test_football_api.py
git commit -m "feat: add COMPETITION toggle to football_api"
```

---

## Task 2: Multi-match-per-day queries in db_utils.py

**Files:**
- Modify: `db_utils.py`

- [ ] **Step 1: Add the new queries**

In `db_utils.py`, add these two functions (place them after `get_match_on_day`):

```python
async def get_matches_on_day(session, day: datetime.date):
    """Fetches all matches on a specific date, ordered by start time."""
    stmt = select(Match).where(func.date(Match.start_time) == day).order_by(Match.start_time.asc())
    return (await session.execute(stmt)).scalars().all()


async def get_open_matches_today(session, now: datetime.datetime = None):
    """Fetches today's matches still open for betting (status NS, more than 5 min before kickoff)."""
    if now is None:
        now = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(minutes=5)
    stmt = (
        select(Match)
        .where(
            func.date(Match.start_time) == now.date(),
            Match.status == 'NS',
            Match.start_time > cutoff,
        )
        .order_by(Match.start_time.asc())
    )
    return (await session.execute(stmt)).scalars().all()
```

The `start_time > now + 5 min` rule matches `handlers.is_betting_allowed` (strict `>`).

- [ ] **Step 2: Remove the now-unused single-match query**

Delete the `get_match_on_day` function from `db_utils.py` (its only caller, `place_bet`, is rewritten in Task 4 to use `get_open_matches_today`):

```python
async def get_match_on_day(session, day: datetime.date):
    """Fetches a match on a specific date."""
    stmt = select(Match).where(func.date(Match.start_time) == day).order_by(Match.start_time.asc())
    return (await session.execute(stmt)).scalars().first()
```

- [ ] **Step 3: Manually verify the queries against an in-memory DB**

Run this throwaway snippet from the repo root (do NOT commit it). `aiosqlite` is already a dependency:

```bash
python3 - <<'PY'
import asyncio, datetime
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from models import Base, Match
import db_utils

async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = datetime.datetime(2026, 6, 12, 12, 0)
    async with Session() as s:
        s.add_all([
            Match(id=1, title="A vs B", start_time=datetime.datetime(2026,6,12,18,0), status='NS'),  # open today
            Match(id=2, title="C vs D", start_time=datetime.datetime(2026,6,12,12,3), status='NS'),  # within 5 min -> closed
            Match(id=3, title="E vs F", start_time=datetime.datetime(2026,6,12,20,0), status='FT'),  # finished
            Match(id=4, title="G vs H", start_time=datetime.datetime(2026,6,13,18,0), status='NS'),  # tomorrow
        ])
        await s.commit()
        day = await db_utils.get_matches_on_day(s, now.date())
        open_today = await db_utils.get_open_matches_today(s, now)
        print("matches_on_day:", [m.id for m in day])    # expect [1, 2, 3]
        print("open_today:", [m.id for m in open_today])  # expect [1]
    await engine.dispose()

asyncio.run(main())
PY
```

Expected output:
```
matches_on_day: [1, 2, 3]
open_today: [1]
```

- [ ] **Step 4: Commit**

```bash
git add db_utils.py
git commit -m "feat: add multi-match-per-day queries, drop single-match query"
```

---

## Task 3: Pure bet-flow helpers in handlers.py

**Files:**
- Modify: `handlers.py`
- Test: `tests/test_bet_helpers.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bet_helpers.py`:

```python
import datetime
from models import Match
from handlers import decide_bet_action, format_match_button_label


def test_decide_bet_action_none():
    assert decide_bet_action([]) == "none"


def test_decide_bet_action_single():
    assert decide_bet_action([object()]) == "single"


def test_decide_bet_action_choose():
    assert decide_bet_action([object(), object()]) == "choose"


def test_format_match_button_label_converts_to_msk():
    # 18:00 UTC -> 21:00 Moscow (UTC+3)
    m = Match(id=1, title="ESP vs GER", start_time=datetime.datetime(2026, 6, 15, 18, 0))
    assert format_match_button_label(m) == "21:00 ESP vs GER"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bet_helpers.py -v`
Expected: FAIL — `ImportError: cannot import name 'decide_bet_action'`.

- [ ] **Step 3: Implement the helpers**

In `handlers.py`, add these after the existing `format_match_time_msk` function (around line 40):

```python
def format_match_button_label(match) -> str:
    """Short label for a match-selection button: '21:00 Home vs Away' in Moscow time."""
    dt = match.start_time
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    msk_dt = dt.astimezone(MSK_TZ)
    return f"{msk_dt.strftime('%H:%M')} {match.title}"


def decide_bet_action(open_matches) -> str:
    """Routes /bet based on how many matches are open today: 'none', 'single', or 'choose'."""
    if not open_matches:
        return "none"
    if len(open_matches) == 1:
        return "single"
    return "choose"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bet_helpers.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add handlers.py tests/test_bet_helpers.py
git commit -m "feat: add pure bet-routing and button-label helpers"
```

---

## Task 4: Rework /bet for multiple matches per day

**Files:**
- Modify: `handlers.py`

This task wires up the keyboard builder, a shared `prompt_or_save` helper, the rewritten `place_bet`, and the new `pick_match` callback. It depends on Tasks 2 and 3.

- [ ] **Step 1: Add the match-choice keyboard builder**

In `handlers.py`, add after the existing `get_bet_confirmation_keyboard` function:

```python
def get_match_choice_keyboard(matches):
    """Inline keyboard with one button per open match; callback data 'betpick:{match_id}'."""
    rows = [
        [InlineKeyboardButton(text=format_match_button_label(m), callback_data=f"betpick:{m.id}")]
        for m in matches
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 2: Add the shared prompt_or_save helper**

In `handlers.py`, add directly above the existing `save_bet` function:

```python
async def prompt_or_save(target_message, user_id, session, match_obj, score, state):
    """If a score is supplied: save it, or ask to confirm overwriting an existing bet.
    If no score: store the match in FSM and prompt the user to send a score."""
    if score is None:
        await state.set_state(BettingStates.waiting_for_score)
        await state.update_data(match_id=match_obj.id)
        await target_message.answer(
            f"⚽ Матч: **{match_obj.title}**\n"
            f"⏰ Начало: {format_match_time_msk(match_obj.start_time)}\n\n"
            f"Пришли свой прогноз (например, `2:1` или `2 1`):",
            parse_mode="Markdown"
        )
        return

    h_score, g_score = score
    existing_bet = await db_utils.get_user_bet(session, user_id, match_obj.id)
    if existing_bet:
        kb = get_bet_confirmation_keyboard(match_obj.id, h_score, g_score)
        msg = (f"⚠️ У тебя уже сделан прогноз на матч **{match_obj.title}**.\n"
               f"Твой прогноз: `{existing_bet.bet_home_score}:{existing_bet.bet_guest_score}`.\n\n"
               f"Хочешь изменить его на `{h_score}:{g_score}`?")
        await target_message.answer(msg, reply_markup=kb, parse_mode="Markdown")
        return

    await save_bet(target_message, user_id, session, match_obj, h_score, g_score)
```

- [ ] **Step 3: Replace the place_bet handler**

Replace the entire existing `place_bet` function (the one decorated with `@router.message(Command("bet"))`) with:

```python
@router.message(Command("bet"))
async def place_bet(message: types.Message, command: CommandObject, state: FSMContext):
    logger.info(f"User {message.from_user.id} called /bet with args: {command.args}")
    now = datetime.datetime.utcnow()

    async with AsyncSessionLocal() as session:
        open_matches = await db_utils.get_open_matches_today(session, now)
        action = decide_bet_action(open_matches)

        if action == "none":
            next_game = await db_utils.get_next_match(session, now)
            msg = "❌ Сегодня нет матчей. Прогнозы принимаются только в дни матчей!"
            if next_game:
                date_str = format_match_time_msk(next_game.start_time)
                msg += f"\n\n📅 Следующая игра:\n**{next_game.title}**\n⏰ {date_str}"
            return await message.answer(msg, parse_mode="Markdown")

        # Parse the optional score argument once.
        score = parse_score(command.args) if command.args else None
        if command.args and not score:
            return await message.answer("❌ Неверный формат. Используйте: `2:1`, `2 1` или `2-1`.")

        if action == "single":
            await prompt_or_save(message, message.from_user.id, session, open_matches[0], score, state)
            return

        # action == "choose": multiple open matches today -> show a picker.
        await state.update_data(pending_score=list(score) if score else None)
        kb = get_match_choice_keyboard(open_matches)
        if score:
            prompt = f"Выбери матч для прогноза `{score[0]}:{score[1]}`:"
        else:
            prompt = "Выбери матч для прогноза:"
        await message.answer(prompt, reply_markup=kb, parse_mode="Markdown")
```

- [ ] **Step 4: Add the pick_match callback handler**

In `handlers.py`, add after `place_bet` (and before `process_bet_score`):

```python
@router.callback_query(F.data.startswith("betpick:"))
async def pick_match(callback: CallbackQuery, state: FSMContext):
    match_id = int(callback.data.split(":")[1])
    now = datetime.datetime.utcnow()

    async with AsyncSessionLocal() as session:
        match_obj = await session.get(Match, match_id)
        if not match_obj or match_obj.status == 'FT' or not is_betting_allowed(match_obj.start_time, now):
            await callback.message.edit_text("❌ Этот матч уже закрыт для прогнозов.", reply_markup=None)
            return await callback.answer()

        data = await state.get_data()
        pending = data.get("pending_score")
        score = tuple(pending) if pending else None

        # Remove the picker buttons, keep pending_score cleared (match_id may be set by prompt_or_save).
        await callback.message.edit_reply_markup(reply_markup=None)
        await state.update_data(pending_score=None)
        await prompt_or_save(callback.message, callback.from_user.id, session, match_obj, score, state)

    await callback.answer()
```

Note: `process_bet_score` (the `waiting_for_score` FSM handler) and `confirm_bet_change` already key off `match_id` stored in state / callback data, so they work unchanged after a pick.

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS — Task 1 (2), Task 3 (4), existing `test_points.py` and `test_bet_logic.py` all green. (`tests/test_logic.py` is a manual script, not collected as failing assertions — if pytest tries to collect it and errors on missing DB, that is pre-existing; ignore.)

- [ ] **Step 6: Commit**

```bash
git add handlers.py
git commit -m "feat: rework /bet with inline match picker for multi-match days"
```

---

## Task 5: Scheduler — multi-match daily reminder and generic copy

**Files:**
- Modify: `scheduler.py`

- [ ] **Step 1: Rework daily_match_reminder**

Replace the entire existing `daily_match_reminder` function with:

```python
async def daily_match_reminder(bot: Bot):
    """At the daily slot: list today's matches, schedule each one's jobs, and notify all users."""
    logger.info("Checking for daily match reminders...")
    now = datetime.datetime.utcnow()
    async with AsyncSessionLocal() as session:
        matches = await db_utils.get_matches_on_day(session, now.date())
        if not matches:
            logger.info("No matches today.")
            return

        logger.info(f"{len(matches)} match(es) today. Scheduling jobs and notifying users.")
        lines = []
        for match_obj in matches:
            time_str = format_match_time_msk(match_obj.start_time)
            lines.append(f"⚽ {time_str} — {match_obj.title}")
            await schedule_match_jobs(bot, match_obj)

        text = "📅 Сегодняшние матчи:\n" + "\n".join(lines) + "\n\nНе забудь сделать прогноз с помощью /bet"
        users = (await session.execute(select(User))).scalars().all()
        await notify_users(bot, users, text)
```

(`select` and `User` are already imported at the top of `scheduler.py`.)

- [ ] **Step 2: Genericize hourly_bet_reminder text**

In `hourly_bet_reminder`, change the message line from:

```python
        msg = f"⏰ Последний шанс!\nВ {time_str} Барселона начинает матч {match_obj.title}.\nТы еще успеешь сделать ставку! Используй /bet прямо сейчас."
```

to:

```python
        msg = f"⏰ Последний шанс!\nВ {time_str} начинается матч {match_obj.title}.\nТы еще успеешь сделать ставку! Используй /bet прямо сейчас."
```

- [ ] **Step 3: Sanity-check the module imports**

Run: `python3 -c "import scheduler; print('ok')"`
Expected: `ok` (no syntax/import errors).

- [ ] **Step 4: Commit**

```bash
git add scheduler.py
git commit -m "feat: daily reminder lists all of today's matches; generic copy"
```

---

## Task 6: Genericize remaining Barça-specific copy in handlers.py

**Files:**
- Modify: `handlers.py`

- [ ] **Step 1: Update format_match_list header**

Change:

```python
    response = "📅 **Ближайшие 5 матчей Барселоны:**\n\n"
```

to:

```python
    response = "📅 **Ближайшие матчи:**\n\n"
```

- [ ] **Step 2: Update the /help text**

In `help_cmd`, change the title and the `/games` line. From:

```python
        "📖 **FC Barcelona Bet Bot - Команды**\n\n"
```

to:

```python
        "📖 **Bet Bot — Команды**\n\n"
```

and from:

```python
        "/games — Посмотреть ближайшие 5 матчей Барселоны.\n"
```

to:

```python
        "/games — Посмотреть ближайшие матчи.\n"
```

- [ ] **Step 3: Update the /start welcome message**

In `start_cmd`, change the new-user welcome from:

```python
            await message.answer(f"🔵🔴 Добро пожаловать, {full_name}, в Club2977 Score Bot! Тут мы пытаемся угадать счет матчей Барселоны! Используйте /help для просмотра команд.")
```

to:

```python
            await message.answer(f"👋 Добро пожаловать, {full_name}, в Score Bot! Тут мы угадываем счёт матчей. Используйте /help для просмотра команд.")
```

- [ ] **Step 4: Verify nothing else references Барселон / Barcelona in user text**

Run: `grep -ni "барсел\|barcelona" handlers.py scheduler.py`
Expected: no matches (or only comments). Fix any remaining user-facing strings the same way.

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS (Tasks 1 & 3 tests + existing tests green).

- [ ] **Step 6: Commit**

```bash
git add handlers.py
git commit -m "chore: genericize Barça-specific copy for competition mode"
```

---

## Task 7: Enable WC mode and document the toggle

**Files:**
- Modify: `.env` (local, gitignored — not committed)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Turn on World Cup mode locally**

Append to `.env` (this file is gitignored, so it is not committed):

```
COMPETITION=WC
```

- [ ] **Step 2: Document the toggle in CLAUDE.md**

In `CLAUDE.md`, in the Commands section's `.env` line, add `COMPETITION` to the list. Change:

```
`.env` is required (loaded via python-dotenv): `BOT_TOKEN`, `FOOTBALL_API_KEY`, `DATABASE_URL` (e.g. `sqlite+aiosqlite:///bot.db`), `ADMIN_ID`.
```

to:

```
`.env` is required (loaded via python-dotenv): `BOT_TOKEN`, `FOOTBALL_API_KEY`, `DATABASE_URL` (e.g. `sqlite+aiosqlite:///bot.db`), `ADMIN_ID`. Optional: `COMPETITION` (e.g. `WC`) — when set, the bot fetches that competition's matches instead of FC Barcelona's; remove the line to revert to Barça.
```

- [ ] **Step 3: Commit the docs (not .env)**

```bash
git add CLAUDE.md
git commit -m "docs: document COMPETITION env toggle"
```

---

## Task 8: Live smoke test (requires a valid API key)

**Files:** none (verification only)

> Skip the API-dependent steps if no working `FOOTBALL_API_KEY` is available yet; the code is complete without them. Replace the placeholder key below with a real free-tier token.

- [ ] **Step 1: Confirm WC fixtures are reachable**

```bash
python3 -c "
import asyncio, os
os.environ['COMPETITION'] = 'WC'
from football_api import FootballAPI
async def m():
    api = FootballAPI()
    print('url:', api._fixtures_url())
    data = await api.get_fixtures()
    print('fetched:', len(data))
    if data: print('sample:', data[0]['homeTeam']['name'], 'vs', data[0]['awayTeam']['name'], data[0]['utcDate'])
asyncio.run(m())
"
```

Expected: `url:` ends in `/competitions/WC/matches`, `fetched:` > 0. If it prints `fetched: 0`, check the API key (see precondition) and the tier's WC access.

- [ ] **Step 2: Run the bot and exercise it in Telegram**

Run: `python main.py`
Then, in Telegram: `/start`, `/games` (should list WC matches), and on a day with multiple matches, `/bet` (should show the inline match picker). Pick a match, send a score, confirm the bet is saved.

- [ ] **Step 3: Stop the bot.** No commit — verification only.

---

## Self-review notes

- **Spec coverage:** toggle (Task 1), multi-match queries (Task 2), inline picker + bet rework (Tasks 3–4), scheduler multi-match + copy (Tasks 5–6), config + docs (Task 7), live verification + key precondition (Task 8). All spec sections covered.
- **Type consistency:** `get_open_matches_today`/`get_matches_on_day` (Task 2) are the exact names called in Task 4/5; `decide_bet_action`, `format_match_button_label`, `get_match_choice_keyboard`, `prompt_or_save` defined in Tasks 3–4 and used consistently; callback prefix `betpick:` matches between keyboard builder and handler.
- **No placeholders:** every code/edit step shows full content; the only intentional placeholder is the API key in Task 8, which is operational, not code.
