# FC Barcelona Bet Bot

A Telegram bot for betting on FC Barcelona matches, featuring real-time fixture syncing, result tracking, and a leaderboard system.

## Project Overview
This project is an asynchronous Python-based Telegram bot built with **aiogram**. It allows users to place bets on FC Barcelona matches, tracks their accuracy, and maintains a competitive leaderboard. It integrates with **API-Football** for fixture and result data.

### Main Technologies
- **aiogram**: Telegram Bot API framework.
- **SQLAlchemy (Async)**: ORM for database management.
- **APScheduler**: For background tasks (syncing fixtures, checking results, reminders).
- **httpx**: For asynchronous API calls to API-Football.
- **python-dotenv**: For managing environment variables.

## Architecture
- `main.py`: Entry point; initializes the bot, database, and scheduler.
- `handlers.py`: Telegram message handlers for user commands (`/start`, `/bet`, `/leaderboard`, etc.).
- `models.py`: SQLAlchemy models for `User`, `Match`, and `Bet`.
- `database.py`: Database engine and session configuration.
- `football_api.py`: Client for interacting with the external Football API.
- `scheduler.py`: Background tasks for match synchronization, result verification, and user notifications.
- `points_calculator.py`: Logic for calculating points based on match outcomes and scores.

## Scoring System
Points are awarded cumulatively based on the following rules:
- **Match Outcome (Win/Draw/Loss)**: +2 points
- **Exact Home Team Score**: +3 points
- **Exact Guest Team Score**: +3 points
- **Exact Goal Difference**: +4 points
- **Exact Total Goals**: +4 points

## Commands
- `/start`: Register and initialize the bot.
- `/bet H:G`: Place or update a bet for the next match today (e.g., `/bet 2:1`).
- `/mybets`: View personal betting history and earned points.
- `/leaderboard`: View the current global rankings.
- `/deleteme`: Delete your account and bet history.
- `/reset_all_scores` (Admin only): Reset all scores in the system.

## Building and Running
### Prerequisites
- Python 3.9+
- A Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- An API Key from [API-Football](https://dashboard.api-football.com/)
- A database URL (e.g., SQLite `sqlite+aiosqlite:///bot.db`)

### Configuration
Create a `.env` file in the root directory with the following variables:
```env
BOT_TOKEN=your_telegram_bot_token
FOOTBALL_API_KEY=your_api_football_key
DATABASE_URL=sqlite+aiosqlite:///bot.db
ADMIN_ID=your_telegram_user_id
```

### Installation
```bash
pip install -r requirements.txt
```
*(Note: If `requirements.txt` is missing, manually install `aiogram`, `sqlalchemy`, `aiosqlite`, `apscheduler`, `httpx`, and `python-dotenv`.)*

### Running the Bot
```bash
python main.py
```

## Development Conventions
- **Asynchronous Code**: All I/O operations (database, API, Telegram) must be `async`.
- **Database Migrations**: Currently uses `Base.metadata.create_all` on startup. For production, consider using Alembic.
- **Timezones**: The bot uses UTC internally for all match times and schedules.
