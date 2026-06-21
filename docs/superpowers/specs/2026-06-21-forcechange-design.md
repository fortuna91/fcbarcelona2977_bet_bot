# Design: /forcechange Admin Command

**Date:** 2026-06-21  
**Status:** Approved

## Problem

The football-data.org API occasionally returns wrong scores. Once `check_results_and_notify` runs and sets `status = "FT"`, there is no way to correct the stored score or recalculate affected bets. Admins need a manual override.

## Scope

- New `/forcechange` command (admin-only)
- Multi-admin support via `ADMIN_IDS` env var (replaces single `ADMIN_ID`)
- All changes land in `handlers.py` (Approach A — flat, consistent with existing patterns)

## Admin Identity

Replace the single `ADMIN_ID` constant with a set and a helper:

```python
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
```

- `.env` gains `ADMIN_IDS=123456,789012` (comma-separated Telegram user IDs)
- `reset_all_scores` guard updated to use `is_admin()`
- Old `ADMIN_ID` env var removed

## FSM

```python
class ForceChangeStates(StatesGroup):
    waiting_for_score = State()
```

FSM data stored between steps: `match_id` (int).

## Keyboard Helpers

```python
def get_forcechange_match_keyboard(matches) -> InlineKeyboardMarkup:
    # One button per match: "DD.MM Title H:G"
    # callback_data: "forcechange_pick:{match_id}"

def get_forcechange_confirm_keyboard(match_id, h, g) -> InlineKeyboardMarkup:
    # ✅ Да  → "confirm_forcechange:{match_id}:{h}:{g}"
    # ❌ Нет → "cancel_forcechange"
```

## Handler Flow (5 handlers)

### 1. `/forcechange` command
- Guard: `not is_admin(user_id)` → reply "🚫 Только для администратора." and return
- Query last 5 `Match` rows where `status == "FT"`, ordered by `start_time DESC`
- If none: reply "Нет завершённых матчей."
- Show inline keyboard via `get_forcechange_match_keyboard`

### 2. `forcechange_pick:{match_id}` callback
- Fetch `Match` by id; guard if not found
- Store `match_id` in FSM data
- Set state `ForceChangeStates.waiting_for_score`
- Edit message to: *"Матч: {title}\nТекущий счёт: {H}:{G}\n\nВведи правильный счёт:"*

### 3. `ForceChangeStates.waiting_for_score` message handler
- Parse with `SCORE_REGEX`; bad format → reply error, stay in state (do not clear)
- Retrieve `match_id` from FSM data
- Send confirmation message with `get_forcechange_confirm_keyboard(match_id, h, g)`
- Clear FSM state (confirmation is stateless — score embedded in callback_data)

### 4. `confirm_forcechange:{match_id}:{h}:{g}` callback
DB work (single session, single commit):
1. Fetch `Match`; record `old_h = match.actual_home_score`, `old_g = match.actual_guest_score`
2. Fetch all `Bet` rows for the match
3. For each bet:
   - `old_pts = bet.points_earned`
   - `new_pts = calculate_points(bet.bet_home_score, bet.bet_guest_score, new_h, new_g)`
   - `bet.points_earned = new_pts`
   - Stash `(bet.user_id, old_pts, new_pts)` for notifications
4. Update `match.actual_home_score = new_h`, `match.actual_guest_score = new_g`
5. Commit
6. Send per-user notification (see Messages section)
7. Reply to admin with summary
8. Edit confirmation message to remove keyboard

### 5. `cancel_forcechange` callback
- Edit message to "Отменено."
- (FSM already cleared in step 3)

## Messages (Russian)

**Per-user notification** (sent to each user who had a bet):
```
⚠️ Счёт матча {match.title} был исправлен!

Старый счёт: {old_h}:{old_g} → Новый счёт: {new_h}:{new_g}
Твой прогноз: {bet_h}:{bet_g}

Очки за матч: {old_pts} → {new_pts}
```

**Admin summary** (sent after commit):
```
✅ Готово! Счёт матча {title} изменён: {old_h}:{old_g} → {new_h}:{new_g}
Пересчитаны очки для {N} участников.
```

Only users with a bet on the corrected match are notified. Non-bettors have nothing to recalculate.

## Edge Cases

| Situation | Handling |
|---|---|
| No finished matches | Reply "Нет завершённых матчей." |
| Bad score format | Stay in `waiting_for_score`, ask again |
| Match has no bets | Commit score update, notify admin "0 участников" |
| Notification delivery fails | Log warning, continue — same pattern as `check_results_and_notify` |
| `ADMIN_IDS` env var empty/missing | `ADMIN_IDS` set is empty; all admin commands return forbidden |

## Files Changed

- `handlers.py` — all changes (ADMIN_IDS constant, `is_admin()`, new FSM, 5 new handlers, 2 new keyboard helpers)
- `.env` (docs only — `ADMIN_ID` → `ADMIN_IDS`)
- `CLAUDE.md` — update ADMIN_ID reference to ADMIN_IDS
