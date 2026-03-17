-- ═══════════════════════════════════════════════════════════════════════════
-- schema.sql  –  Run this ONCE to set up the database
-- Usage:  mysql -u root -p < schema.sql
-- ═══════════════════════════════════════════════════════════════════════════

-- 1. Create the database (if not already done)
CREATE DATABASE IF NOT EXISTS audio_stems
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE audio_stems;

-- ─── Users ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    email         VARCHAR(255)    NOT NULL UNIQUE,
    password_hash VARCHAR(255)    NOT NULL,          -- Werkzeug hashed password
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─── Uploads / Jobs ──────────────────────────────────────────────────────────
-- Tracks every separation job per user.
-- status: pending | processing | done | error
CREATE TABLE IF NOT EXISTS uploads (
    id            INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    user_id       INT UNSIGNED    NOT NULL,
    original_name VARCHAR(255)    NOT NULL,          -- original filename from user
    stored_name   VARCHAR(255)    NOT NULL,          -- UUID-based name on disk
    status        VARCHAR(20)     NOT NULL DEFAULT 'pending',
    task_id       VARCHAR(155)    NULL,              -- Celery task UUID
    output_zip    VARCHAR(255)    NULL,              -- path to downloadable ZIP
    error_msg     TEXT            NULL,
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                         ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_uploads_user
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─── Optional: index for fast user history lookups ───────────────────────────
CREATE INDEX idx_uploads_user_id ON uploads (user_id);
