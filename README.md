# Telegram Student Verification Bot

Production-ready async Telegram bot that verifies group membership and student identity against an existing SQLite database, then securely returns the student's existing username and password.

All user-facing bot messages are in Persian.

## Features

- Private-chat only verification flow
- Required Telegram group membership check
- Contact sharing with ownership validation
- Exact full-name and student-number matching (after Persian/Arabic normalization)
- Iranian National ID format and checksum validation
- Atomic one-to-one claim of student records by Telegram user ID
- Retry limits and basic per-user rate limiting
- Secure logging (no passwords, national IDs, phones, or credentials)

## Requirements

- Python 3.12+
- An existing SQLite database with a `students` table
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- The bot added to the required group (preferably as administrator)

## Create the bot with BotFather

1. Open Telegram and chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts.
3. Copy the bot token.
4. Optionally disable group privacy if needed for your deployment model; membership checks use `getChatMember` and work when the bot can see the group.

## Install dependencies

```bash
cd /path/to/bhzd-exam-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
BOT_TOKEN=123456:ABC-DEF...
REQUIRED_GROUP_ID=-1001234567890
DATABASE_PATH=students.db
ADMIN_USERNAME=@behzadmminaei
LOG_LEVEL=INFO
```

Required variables are validated at startup.

## Obtain the Telegram group ID

1. Add the bot to the target group.
2. Send a message in the group.
3. Open `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` in a browser.
4. Find `"chat":{"id":-100...}` for the group and set `REQUIRED_GROUP_ID` to that value.

You can also forward a group message to bots such as `@userinfobot` / `@RawDataBot` to read the chat id.

## Why the bot may need administrator access

Telegram's `getChatMember` API is used to verify membership. In many setups the bot must be a member of the group, and **administrator rights improve reliability** of membership checks. If the bot cannot check membership, users see a safe error and are asked to retry or contact the admin.

Valid membership statuses:

- `member`
- `administrator`
- `creator`
- `restricted` (still in the group)

## Prepare the SQLite database

Expected table shape (column names are configurable in `config.py`):

```sql
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    student_number TEXT NOT NULL UNIQUE,
    national_id TEXT,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    telegram_user_id INTEGER,
    telegram_username TEXT,
    phone_number TEXT,
    verified_at TEXT
);
```

The bot **never** creates or replaces your production database. Point `DATABASE_PATH` at your existing file.

If verification columns are missing, run the additive migration:

```bash
sqlite3 students.db < migration.sql
```

`migration.sql` uses `ALTER TABLE ... ADD COLUMN`. If a column already exists, skip that line and continue. The unique index for `telegram_user_id` is also created by the bot at startup when possible.

## Run the bot

```bash
source .venv/bin/activate
python app.py
```

## Run tests

```bash
source .venv/bin/activate
pytest
```

Tests use temporary SQLite databases and never modify your production database.

## Deploy with systemd

1. Install the project on the server and configure `.env`.
2. Copy the unit file:

```bash
sudo cp deploy/telegram-student-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-student-bot
sudo systemctl status telegram-student-bot
```

Edit paths/user in `deploy/telegram-student-bot.service` before enabling.

## Deploy with Docker

```bash
docker compose up -d --build
```

Mount your real `students.db` and `.env` as shown in `docker-compose.yml`.

## Verification flow

1. `/start` — greeting + group membership check
2. Share phone number via Telegram contact button
3. Enter exact full name (National ID / Golestan spelling)
4. Enter student number (must match the same DB record)
5. Enter National ID (10 digits + checksum)
6. Bot atomically claims the record and sends username/password in monospace HTML

Commands:

- `/start` — start or restart
- `/cancel` — cancel and clear temporary state
- `/help` — Persian help text

## Security notes

- Credentials are sent only after full verification and a successful claim (`rowcount == 1` or same-user re-verify).
- One Telegram user ID maps to at most one student record (application checks + unique partial index).
- Generic error messages avoid database enumeration.
- Sensitive values are never written to logs.
