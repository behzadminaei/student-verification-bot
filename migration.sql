-- Additive migration for student verification columns.
-- Run against your existing database:
--   sqlite3 students.db < migration.sql
--
-- SQLite cannot easily drop columns; this migration only adds what is missing.
-- If a column already exists, the corresponding ALTER TABLE will fail — skip that line.

ALTER TABLE students ADD COLUMN national_id TEXT;
ALTER TABLE students ADD COLUMN telegram_user_id INTEGER;
ALTER TABLE students ADD COLUMN telegram_username TEXT;
ALTER TABLE students ADD COLUMN phone_number TEXT;
ALTER TABLE students ADD COLUMN verified_at TEXT;
ALTER TABLE students ADD COLUMN exam_url TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_students_telegram_user_id
ON students (telegram_user_id)
WHERE telegram_user_id IS NOT NULL;
