# World Cup 2026 Mode — Design

**Date:** 2026-06-12
**Status:** Approved (pending spec review)

## Goal

Temporarily switch the bet bot from fetching FC Barcelona matches to fetching
World Cup 2026 matches, while keeping the switch reversible with no code change.
Users place score predictions on **every** WC match each day (full tournament
pool), not just one match per day.

## Decisions (locked)

1. **Betting scope:** users can bet on all of a day's matches (group stage has
   3–4 matches/day), not a single featured match.
2. **Revert mechanism:** an env-var toggle. `COMPETITION=WC` enables World Cup
   mode; removing the line restores FC Barcelona mode. No code change to revert.
3. **Match selection UI:** inline keyboard buttons — `/bet` lists the day's open
   matches as tappable buttons; tapping one then collects the score.

## Known precondition / risk

- The `FOOTBALL_API_KEY` currently in `.env` is **invalid** — football-data.org
  returns `400 "Your API token is invalid."` even for the existing Barça endpoint
  (`/teams/81/matches`). A valid key is required for the bot to fetch anything.
- World Cup (`WC`) is included in football-data.org's free tier, so a valid
  free-tier key is expected to work, but this could not be verified live because
  the local key is rejected. Verify WC reachability once a working key is in place.
- WC 2026 group-stage opponents may be listed as placeholders by the API until
  the draw is finalized; team names come straight from the API and need no
  special handling.

## Architecture

The change adds a **competition toggle** at the data-source layer and reworks the
betting flow to handle multiple matches per day. The scheduler and scoring logic
are already keyed per match and need almost no change.

### 1. `football_api.py` — data-source toggle

- In `__init__`, read `self.competition = os.getenv("COMPETITION")` (e.g. `"WC"`).
  Keep `self.team_id = 81`.
- Extract URL building into a pure helper so it is unit-testable without a network
  call:

  ```python
  def _fixtures_url(self) -> str:
      if self.competition:
          return f"{self.base_url}/competitions/{self.competition}/matches"
      return f"{self.base_url}/teams/{self.team_id}/matches"
  ```

- `get_fixtures()` uses `self._fixtures_url()`. The response shape is identical
  for both endpoints: `data["matches"]`, each item having `id`, `utcDate`,
  `status`, `homeTeam`, `awayTeam`, `score`.
- `get_fixture_by_id()` is unchanged — `/matches/{id}` works for any match id.

### 2. `scheduler.py` — minimal change

- `sync_matches()` already iterates `data` (all matches) and upserts each, mapping
  the API status set to `FT` (FINISHED) / `NS` (everything else). World Cup mode
  simply yields more rows; no logic change.
- `schedule_match_jobs()`, `check_results_and_notify()`, and `check_upcoming_jobs()`
  are already keyed per `match_id` (job ids `check_{id}`, `hourly_{id}`), so they
  handle multiple matches per day unchanged.
- `daily_match_reminder()` currently selects one match for "today" via
  `.first()`. Change it to fetch **all** of today's matches: schedule each match's
  jobs and send a reminder that lists today's matches.
- `hourly_bet_reminder()` text is made generic (see Copy section).

### 3. `db_utils.py` — multi-match-per-day queries

- Add `get_matches_on_day(session, day)` returning **all** matches on `day`
  ordered by `start_time` (the existing `get_match_on_day` returns only the
  first; keep it or replace its callers).
- Add a helper for "today's matches still open for betting": status `NS` and
  more than 5 minutes before kickoff. This mirrors the `is_betting_allowed`
  rule (`(start_time - now) > 5 min`).

### 4. `handlers.py` — bet flow rework

New `/bet` behavior based on how many of today's matches are still open:

- **0 open matches today** → existing "no matches today" message plus next-match
  info (reuse `db_utils.get_next_match`).
- **1 open match** → exactly the current flow: accept `/bet 2:1` directly, or
  prompt for the score via the existing FSM `waiting_for_score` state.
- **2+ open matches** → reply with an inline keyboard, one button per match
  labelled with kickoff time + teams (e.g. `21:00 ESP vs GER`), callback data
  `betpick:{match_id}`. Callback data stays well under Telegram's 64-byte limit.
  - If the user passed a score (`/bet 2:1`), stash the parsed score in FSM data
    so it is applied immediately after they pick a match.
  - Otherwise, after the user taps a match, transition to `waiting_for_score`
    (storing `match_id`) and prompt for the score.

New callback handler `betpick:{match_id}`:
- Load the match, re-check it is still open for betting.
- If FSM holds a pending score → run the save / change-confirmation path directly.
- Else → set `waiting_for_score` with `match_id` and prompt for the score.

The existing change-confirmation callback (`confirm_bet_change:{match_id}:{h}:{g}`)
is already keyed by `match_id` and is reused unchanged. The
`process_bet_score` FSM handler already stores `match_id` in state and is reused.

### 5. Copy / localization

All UI remains Russian. Replace Barça-specific strings with generic wording that
reads correctly in both modes:

- `format_match_list` header: "Ближайшие матчи" (drop "Барселоны").
- `hourly_bet_reminder`: "Скоро начало матча" (drop "Барселона начинает матч").
- `daily_match_reminder`: list today's matches generically.
- `/help`, `/start`, `/rules` Barça references softened to generic match wording.

No `COMPETITION_NAME` label env var (YAGNI — excluded by decision).

## Data flow

```
APScheduler 02:00 cron ──▶ sync_matches ──▶ FootballAPI.get_fixtures()
                                              └─ COMPETITION set? /competitions/WC/matches
                                              └─ else            /teams/81/matches
                                          ──▶ upsert Match rows (FT/NS)

/bet ──▶ today's open matches?
          0 ─▶ "no matches" + next match
          1 ─▶ score prompt / direct save
          2+ ─▶ inline buttons (betpick:{id}) ─▶ score prompt / direct save

match end ──▶ check_results_and_notify (per match) ──▶ calculate_points ──▶ notify + leaderboard
```

## Error handling

- API failures already return `[]`/`None` from `FootballAPI` and are logged;
  `sync_matches` wraps the loop in try/except. No change.
- `betpick` re-validates the match exists and is still open before saving, so a
  stale button (match started while the keyboard was open) yields the existing
  "too late" message rather than an error.
- Invalid score input continues to use the existing `parse_score` / `SCORE_REGEX`
  validation and error messages.

## Testing

- **New pure-logic unit tests** (no DB, matching repo convention):
  - `FootballAPI._fixtures_url()` returns the competition URL when `COMPETITION`
    is set and the team URL when it is not.
  - Any new pure helper extracted during implementation.
- **Existing tests stay green:** `tests/test_points.py`, `tests/test_bet_logic.py`.
- `tests/test_logic.py` remains a manual DB script (not a pytest test) — unchanged.
- Note: `pytest` is not in `requirements.txt`; install separately to run tests.

## Out of scope

- Running Barça and WC simultaneously / per-competition leaderboard scoping.
- A `COMPETITION_NAME` display label.
- Migrations or schema changes (none needed; `Match` schema is unchanged).
- Fixing/rotating the invalid API key (operational task, flagged as a precondition).
