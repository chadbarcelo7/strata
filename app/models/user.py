"""
app/models/user.py
──────────────────
SQLAlchemy ORM model for the `users` table.
Flask-Login requires the four properties/methods below.
"""

from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager


class User(UserMixin, db.Model):
    """
    Represents a registered user.
    UserMixin provides default implementations of:
        is_authenticated, is_active, is_anonymous, get_id()
    """

    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email         = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at    = db.Column(db.DateTime, server_default=db.func.now())

    # One user → many uploads
    uploads = db.relationship("Upload", backref="user", lazy="dynamic",
                               cascade="all, delete-orphan")

    # ── Password helpers ──────────────────────────────────────────────────
    def set_password(self, raw_password: str):
        """Hash and store a plain-text password."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Return True if the supplied password matches the stored hash."""
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"


# ── Flask-Login user loader ───────────────────────────────────────────────────
@login_manager.user_loader
def load_user(user_id: str):
    """
    Flask-Login calls this to reload the user from the session.
    Must return None (not raise) if user doesn't exist.
    """
    return db.session.get(User, int(user_id))
