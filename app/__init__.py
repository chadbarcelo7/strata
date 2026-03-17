"""
app/__init__.py
───────────────
Application Factory Pattern.
Creates and configures the Flask app, extensions, and blueprints.
"""

import os
import sys

# ── Ensure the project root is on sys.path ────────────────────────────────────
_APP_DIR  = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_APP_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# ── Shared extension instances ────────────────────────────────────────────────
db            = SQLAlchemy()
login_manager = LoginManager()


def create_app(env: str = None) -> Flask:
    from config import config_map

    app = Flask(__name__)

    # ── Load Configuration ─────────────────────────────────────────────────
    env = env or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_map.get(env, config_map["development"]))

    # ── Ensure upload/output folders exist ────────────────────────────────
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["OUTPUT_FOLDER"], exist_ok=True)

    # ── Bind extensions ────────────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view         = "auth.login"
    login_manager.login_message_category = "warning"

    # ── Register Blueprints ────────────────────────────────────────────────
    from app.routes.auth       import auth_bp
    from app.routes.main       import main_bp
    from app.routes.upload     import upload_bp
    from app.routes.downloader import downloader_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(downloader_bp)

    return app
