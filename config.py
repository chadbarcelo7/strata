"""
config.py
─────────
Centralised configuration loaded from environment variables (.env).
Different classes let you switch environments easily.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # Read .env file into os.environ


class Config:
    """Base configuration shared by all environments."""

    # ── Flask Security ──────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-please-change")

    # ── Database (SQLite — no server needed) ───────────────────────────────
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(os.path.dirname(__file__), "groovefarm.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Silence deprecation warning

    # ── File Storage — local Downloads/Strata_Stem (no hosting storage used) ──
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", 500)) * 1024 * 1024
    _STRATA_ROOT  = os.path.join(os.path.expanduser("~"), "Downloads", "Strata_Stem")
    UPLOAD_FOLDER = os.path.join(_STRATA_ROOT, "download")
    OUTPUT_FOLDER = os.path.join(_STRATA_ROOT, "Stem_output")
    ALLOWED_EXTENSIONS = {"mp3", "wav", "flac", "ogg", "m4a", "aiff"}

    # ── Celery (background tasks) ───────────────────────────────────────────
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    # ── Demucs ──────────────────────────────────────────────────────────────
    DEMUCS_MODEL = os.environ.get("DEMUCS_MODEL", "htdemucs")

    # ── Groq AI ─────────────────────────────────────────────────────────────
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

    # ── FFmpeg ───────────────────────────────────────────────────────────────
    FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


# Dictionary lets run.py pick the right class with an env var
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
