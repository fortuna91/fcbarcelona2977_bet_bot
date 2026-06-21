# /forcechange Admin Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/forcechange` admin command that lets admins correct a finished match score and automatically recalculates points for every user who bet on that match.

**Architecture:** All changes land in `handlers.py`. `ADMIN_ID` (single int) is replaced by `ADMIN_IDS` (set of ints) plus an `is_admin()` helper. A new `ForceChangeStates` FSM and five new handlers implement the inline-keyboard flow. Notifications reuse the same `bot.send_message` try/except pattern already used in `scheduler.py`.

**Tech Stack:** Python 3.11+, aiogram 3.x, SQLAlchemy async, APScheduler, pytest

---

## File Map

| File | Change |
|---|---|
| `handlers.py` | Replace `ADMIN_ID` constant; add `is_admin()`; add `ForceChangeStates`; add 2 keyboard helpers; add 5 handlers; update `reset_all_scores` guard |
| `tests/test_admin_helpers.py` | New — unit tests for `is_admin()` and both keyboard helpers |
| `CLAUDE.md` | Update `ADMIN_ID` → `ADMIN_IDS` in the env-var list |

---

### Task 1: Replace ADMIN_ID with ADMIN_IDS + is_admin()

**Files:**
- Modify: `handlers.py` (lines 25–26, and the `reset_all_scores` guard at line 555)
- Create: `tests/test_admin_helpers.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_admin_helpers.py`:

```python
import handlers


def test_is_admin_returns_true_for_known_id(monkeypatch):
    monkeypatch.setattr(handlers, "ADMIN_IDS", {111, 222})
    assert handlers.is_admin(111) is True


def test_is_admin_returns_false_for_unknown_id(monkeypatch):
    monkeypatch.setattr(handlers, "ADMIN_IDS", {111, 222})
    assert handlers.is_admin(333) is False


def test_is_admin_empty_set_always_false(monkeypatch):
    monkeypatch.setattr(handlers, "ADMIN_IDS", set())
    assert handlers.is_admin(111) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_admin_helpers.py -v
```

Expected: `AttributeError: module 'handlers' has no attribute 'is_admin'`

- [ ] **Step 3: Replace ADMIN_ID constant and add is_admin() in handlers.py**

Replace lines 25–26 in `handlers.py`:

```python
# Before:
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# After:
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
```

- [ ] **Step 4: Update the reset_all_scores guard**

In `handlers.py`, find `reset_scores` (around line 553). Change the guard:

```python
# Before:
if message.from_user.id != ADMIN_ID:

# After:
if not is_admin(message.from_user.id):
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_admin_helpers.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add handlers.py tests/test_admin_helpers.py
git commit -m "feat: replace ADMIN_ID with ADMIN_IDS set for multi-admin support"
```

---

### Task 2: ForceChangeStates FSM + keyboard helpers

**Files:**
- Modify: `handlers.py` (after `BettingStates` class; after `get_match_choice_keyboard`)
- Modify: `tests/test_admin_helpers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_admin_helpers.py`:

```python
import datetime
from unittest.mock import MagicMock
from handlers import get_forcechange_match_keyboard, get_forcechange_confirm_keyboard


def test_forcechange_match_keyboard_label_and_callback():
    m = MagicMock()
    m.id = 42
    m.start_time = datetime.datetime(2026, 6, 21, 18, 0)  # 21:00 MSK
    m.title = "Brazil vs Argentina"
    m.actual_home_score = 2
    m.actual_guest_score = 1

    kb = get_forcechange_match_keyboard([m])
    btn = kb.inline_keyboard[0][0]

    assert "21.06" in btn.text
    assert "Brazil vs Argentina" in btn.text
    assert "2:1" in btn.text
    assert btn.callback_data == "forcechange_pick:42"


def test_forcechange_match_keyboard_multiple_matches():
    matches = [MagicMock(id=i, start_time=datetime.datetime(2026, 6, i + 1, 18, 0),
                         title=f"Match {i}", actual_home_score=i, actual_guest_score=0)
               for i in range(1, 4)]
    kb = get_forcechange_match_keyboard(matches)
    assert len(kb.inline_keyboard) == 3


def test_forcechange_confirm_keyboard_yes_callback():
    kb = get_forcechange_confirm_keyboard(99, 3, 0)
    yes_btn = kb.inline_keyboard[0][0]
    assert yes_btn.callback_data == "confirm_forcechange:99:3:0"
    assert "Да" in yes_btn.text


def test_forcechange_confirm_keyboard_no_callback():
    kb = get_forcechange_confirm_keyboard(99, 3, 0)
    no_btn = kb.inline_keyboard[0][1]
    assert no_btn.callback_data == "cancel_forcechange"
    assert "Нет" in no_btn.text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_admin_helpers.py -v
```

Expected: 4 new tests fail with `ImportError` or `AttributeError`

- [ ] **Step 3: Add ForceChangeStates to handlers.py**

After the `BettingStates` class (after line 22):

```python
class ForceChangeStates(StatesGroup):
    waiting_for_score = State()
```

- [ ] **Step 4: Add keyboard helpers to handlers.py**

After `get_match_choice_keyboard` (after line 101):

```python
def get_forcechange_match_keyboard(matches) -> InlineKeyboardMarkup:
    rows = []
    for m in matches:
        dt = m.start_time
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        day = dt.astimezone(MSK_TZ).strftime("%d.%m")
        label = f"{day} {m.title} {m.actual_home_score}:{m.actual_guest_score}"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"forcechange_pick:{m.id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_forcechange_confirm_keyboard(match_id: int, h: int, g: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да", callback_data=f"confirm_forcechange:{match_id}:{h}:{g}"
                ),
                InlineKeyboardButton(text="❌ Нет", callback_data="cancel_forcechange"),
            ]
        ]
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_admin_helpers.py -v
```

Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add handlers.py tests/test_admin_helpers.py
git commit -m "feat: add ForceChangeStates FSM and forcechange keyboard helpers"
```

---

### Task 3: /forcechange command + match pick callback

**Files:**
- Modify: `handlers.py` (add after `reset_scores` handler at the bottom)

- [ ] **Step 1: Add the /forcechange command handler**

Append to `handlers.py`:

```python
@router.message(Command("forcechange"))
async def forcechange_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("🚫 Только для администратора.")

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Match)
            .where(Match.status == "FT")
            .order_by(Match.start_time.desc())
            .limit(5)
        )
        matches = (await session.execute(stmt)).scalars().all()

    if not matches:
        return await message.answer("Нет завершённых матчей.")

    kb = get_forcechange_match_keyboard(matches)
    await message.answer("Выбери матч для исправления счёта:", reply_markup=kb)
```

- [ ] **Step 2: Add the match pick callback handler**

Append to `handlers.py`:

```python
@router.callback_query(F.data.startswith("forcechange_pick:"))
async def forcechange_pick(callback: CallbackQuery, state: FSMContext):
    match_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        match_obj = await session.get(Match, match_id)

    if not match_obj:
        await callback.message.edit_text("Матч не найден.", reply_markup=None)
        return await callback.answer()

    await state.set_state(ForceChangeStates.waiting_for_score)
    await state.update_data(match_id=match_id)

    await callback.message.edit_text(
        f"Матч: **{match_obj.title}**\n"
        f"Текущий счёт: `{match_obj.actual_home_score}:{match_obj.actual_guest_score}`\n\n"
        f"Введи правильный счёт:",
        reply_markup=None,
        parse_mode="Markdown",
    )
    await callback.answer()
```

- [ ] **Step 3: Run the full test suite to check nothing broke**

```bash
pytest tests/test_admin_helpers.py tests/test_bet_helpers.py tests/test_bet_logic.py tests/test_points.py -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add handlers.py
git commit -m "feat: add /forcechange command and match selection callback"
```

---

### Task 4: Score input, confirmation, and cancel handlers

**Files:**
- Modify: `handlers.py` (append remaining 3 handlers)

- [ ] **Step 1: Add the score input handler**

Append to `handlers.py`:

```python
@router.message(ForceChangeStates.waiting_for_score)
async def forcechange_score_input(message: types.Message, state: FSMContext):
    score = parse_score(message.text)
    if not score:
        return await message.answer(
            "❌ Неверный формат. Введи счёт в формате `2:1` или `2 1`.",
            parse_mode="Markdown",
        )

    new_h, new_g = score
    data = await state.get_data()
    match_id = data["match_id"]

    async with AsyncSessionLocal() as session:
        match_obj = await session.get(Match, match_id)

    if not match_obj:
        await state.clear()
        return await message.answer("Матч не найден.")

    await state.clear()
    kb = get_forcechange_confirm_keyboard(match_id, new_h, new_g)
    await message.answer(
        f"Изменить счёт матча **{match_obj.title}**?\n"
        f"Текущий: `{match_obj.actual_home_score}:{match_obj.actual_guest_score}` → Новый: `{new_h}:{new_g}`",
        reply_markup=kb,
        parse_mode="Markdown",
    )
```

- [ ] **Step 2: Add the confirm callback handler**

Append to `handlers.py`:

```python
@router.callback_query(F.data.startswith("confirm_forcechange:"))
async def confirm_forcechange(callback: CallbackQuery):
    parts = callback.data.split(":")
    match_id = int(parts[1])
    new_h = int(parts[2])
    new_g = int(parts[3])

    async with AsyncSessionLocal() as session:
        match_obj = await session.get(Match, match_id)
        if not match_obj:
            await callback.message.edit_text("Матч не найден.", reply_markup=None)
            return await callback.answer()

        old_h = match_obj.actual_home_score
        old_g = match_obj.actual_guest_score

        stmt_bets = select(Bet).where(Bet.match_id == match_id)
        bets = (await session.execute(stmt_bets)).scalars().all()

        user_updates = []
        for bet in bets:
            old_pts = bet.points_earned
            new_pts = calculate_points(
                bet.bet_home_score, bet.bet_guest_score, new_h, new_g
            )
            bet.points_earned = new_pts
            user_updates.append(
                (bet.user_id, bet.bet_home_score, bet.bet_guest_score, old_pts, new_pts)
            )

        match_obj.actual_home_score = new_h
        match_obj.actual_guest_score = new_g
        await session.commit()

    for user_id, bet_h, bet_g, old_pts, new_pts in user_updates:
        try:
            await callback.bot.send_message(
                user_id,
                f"⚠️ Счёт матча {match_obj.title} был исправлен!\n\n"
                f"Старый счёт: {old_h}:{old_g} → Новый счёт: {new_h}:{new_g}\n"
                f"Твой прогноз: {bet_h}:{bet_g}\n\n"
                f"Очки за матч: {old_pts} → {new_pts}",
            )
        except Exception as e:
            logger.warning(f"Failed to notify user {user_id} about score correction: {e}")

    await callback.message.edit_text(
        f"✅ Готово! Счёт матча {match_obj.title} изменён: {old_h}:{old_g} → {new_h}:{new_g}\n"
        f"Пересчитаны очки для {len(user_updates)} участников.",
        reply_markup=None,
    )
    await callback.answer()
```

- [ ] **Step 3: Add the cancel callback handler**

Append to `handlers.py`:

```python
@router.callback_query(F.data == "cancel_forcechange")
async def cancel_forcechange(callback: CallbackQuery):
    await callback.message.edit_text("Отменено.", reply_markup=None)
    await callback.answer()
```

- [ ] **Step 4: Run the full test suite**

```bash
pytest tests/test_admin_helpers.py tests/test_bet_helpers.py tests/test_bet_logic.py tests/test_points.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add handlers.py
git commit -m "feat: add score input, confirmation and cancel handlers for /forcechange"
```

---

### Task 5: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the env-var list in CLAUDE.md**

Find the line:

```
`.env` is required (loaded via python-dotenv): `BOT_TOKEN`, `FOOTBALL_API_KEY`, `DATABASE_URL` (e.g. `sqlite+aiosqlite:///bot.db`), `ADMIN_ID`.
```

Replace with:

```
`.env` is required (loaded via python-dotenv): `BOT_TOKEN`, `FOOTBALL_API_KEY`, `DATABASE_URL` (e.g. `sqlite+aiosqlite:///bot.db`), `ADMIN_IDS` (comma-separated Telegram user IDs of admins, e.g. `123456,789012`).
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md — ADMIN_ID → ADMIN_IDS"
```
