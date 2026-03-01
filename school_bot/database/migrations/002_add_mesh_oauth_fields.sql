-- database/migrations/002_add_mesh_oauth_fields.sql
-- Добавляет поля для OAuth2 авторизации через OctoDiary/mos.ru

-- Новые OAuth-поля для users (все зашифрованы)
ALTER TABLE users ADD COLUMN mesh_refresh_token TEXT;    -- OAuth refresh_token (encrypted)
ALTER TABLE users ADD COLUMN mesh_client_id TEXT;         -- OAuth client_id (encrypted)
ALTER TABLE users ADD COLUMN mesh_client_secret TEXT;     -- OAuth client_secret (encrypted)
ALTER TABLE users ADD COLUMN mesh_profile_id INTEGER;     -- profile_id из get_users_profile_info
ALTER TABLE users ADD COLUMN mesh_role TEXT;              -- Роль: parent/student

-- person_id нужен для events API (расписание)
ALTER TABLE children ADD COLUMN person_id TEXT;           -- contingent_guid из OctoDiary
ALTER TABLE children ADD COLUMN class_unit_id INTEGER;    -- class_unit_id из OctoDiary
