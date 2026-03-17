"""
app/routes/auth.py
──────────────────
Authentication routes: register, login, logout.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User

# Blueprint groups related routes under a common prefix
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# ── Registration ──────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Show registration form (GET) or process it (POST)."""

    # Already logged in? Send them home.
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")

        # ── Validation ────────────────────────────────────────────────────
        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("auth/register.html")

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "warning")
            return render_template("auth/register.html")

        # ── Create user ───────────────────────────────────────────────────
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Show login form (GET) or authenticate the user (POST)."""

    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html")

        # Log the user in and remember them across browser sessions
        login_user(user, remember=True)
        flash("Welcome back!", "success")

        # Redirect to the page they tried to visit, or home
        next_page = request.args.get("next")
        return redirect(next_page or url_for("main.index"))

    return render_template("auth/login.html")


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
