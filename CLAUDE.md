# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Telegram bot (aiogram) for predicting FC Barcelona match scores. Users place a score prediction per match; the bot fetches results, awards points, and maintains a leaderboard. Async throughout (database, HTTP, Telegram).

## Commands

```bash
pip install -r requirements.txt   # pytest is NOT in requirements; pip install pytest separately
python main.py                    # run the bot (needs .env, see below)
pytest                            # run unit tests
pytest tests/test_points.py       # run a single test file
docker compose up --build         # run containerized
```

`.env` is required (loaded via python-dotenv): `BOT_TOKEN`, `FOOTBALL_API_KEY`, `DATABASE_URL` (e.g. `sqlite+aiosqlite:///bot.db`), `ADMIN_ID`. Optional: `COMPETITION` (e.g. `WC`) — when set, the bot fetches that football-data.org competition's matches instead of FC Barcelona's; remove the line to revert to Barça.

Note on tests: `tests/test_points.py` and `tests/test_bet_logic.py` are real pytest unit tests (pure-logic, no DB). `tests/test_logic.py` is NOT a pytest test — it's a manual `asyncio.run` script that queries a live DB and will fail/error under pytest collection if no DB is configured.

## Architecture

Three layers, all async:

- **`main.py`** — entry point. Initializes DB (`init_db`), creates the aiogram `Bot`/`Dispatcher`, registers `handlers.router`, starts `setup_scheduler`, then `start_polling`. The startup `sync_matches()` call is commented out — fixtures are populated by the scheduler's 2 AM cron or lazily by `/games`.
- **`handlers.py`** — all Telegram command handlers on a single `router`. Uses an FSM (`BettingStates.waiting_for_score`) so `/bet` works both with args (`/bet 2:1`) and as a two-step conversation. Bet changes go through an inline-keyboard confirmation callback.
- **`scheduler.py`** — APScheduler (`AsyncIOScheduler`, UTC) background jobs.

Data access is split: `db_utils.py` holds reusable read queries; `database.py` owns the engine + `AsyncSessionLocal`; `models.py` defines `User`/`Match`/`Bet` (SQLAlchemy, cascade deletes). Schema is created via `Base.metadata.create_all` on startup — **there are no migrations**, so model changes won't alter existing tables.

### External data: football-data.org

`football_api.py` talks to **football-data.org v4** (despite some comments/README mentioning "API-Football" — that's stale). Auth is `X-Auth-Token`. `team_id = 81` is FC Barcelona. `get_fixtures()` hits `/teams/{id}/matches`; `get_fixture_by_id()` hits `/matches/{id}`. The `Match.id` primary key IS the football-data.org match id.

`sync_matches()` in `scheduler.py` maps the API shape into the DB: `utcDate` → naive UTC `start_time`, and the API's rich status set (FINISHED/SCHEDULED/TIMED/IN_PLAY/…) is collapsed to just **`FT`** (finished) or **`NS`** (anything else). Scores come from `score.fullTime.{home,away}`.

### Scheduling model

- Daily `sync_matches` cron at 02:00 UTC; daily reminder at 06:00 UTC.
- On startup, `check_upcoming_jobs` re-schedules per-match jobs for `NS` matches within 24h (APScheduler jobs are in-memory, so they're lost on restart and must be rebuilt).
- Per match, `schedule_match_jobs` registers: a result poller (`check_results_and_notify`, every 5 min starting kickoff+110 min, self-removes once `FT`) and a one-shot reminder 1h before kickoff. Job ids: `check_{match_id}`, `hourly_{match_id}`.

### Scoring

`points_calculator.calculate_points` is the single source of truth, cumulative (max 6): +2 outcome, +1 exact home, +1 exact guest, +1 goal diff, +1 total goals. Computed in `check_results_and_notify` when a match flips to `FT`.

## Conventions

- **All user-facing text is in Russian.** Keep it that way.
- **Times: UTC internally, displayed in Moscow time** (`format_match_time_msk`, "МСК"). This helper is duplicated in both `handlers.py` and `scheduler.py`.
- Betting cutoff is 5 minutes before kickoff (`is_betting_allowed`); the boundary is strict `> 5min` (exactly 5 min is too late — see `tests/test_bet_logic.py`).
- Score input is parsed leniently via `SCORE_REGEX` — accepts `2:1`, `2 1`, `2-1`.
