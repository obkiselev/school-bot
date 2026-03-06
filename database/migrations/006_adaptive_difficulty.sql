-- Migration 006: Add difficulty column to test_sessions
ALTER TABLE test_sessions ADD COLUMN difficulty TEXT DEFAULT NULL;
