"""
app/routes/upload.py
──────────────────────
Routes for file upload, job status polling, and stem download.
"""

import os
import uuid
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, jsonify, send_from_directory, abort)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.upload import Upload
from app.services.tasks import run_separation

upload_bp = Blueprint("upload", __name__, url_prefix="/upload")


def _allowed_file(filename: str) -> bool:
    """Return True if the file extension is in ALLOWED_EXTENSIONS."""
    from flask import current_app
    allowed = current_app.config["ALLOWED_EXTENSIONS"]
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


# ── Upload Page ───────────────────────────────────────────────────────────────

@upload_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    """
    GET  → display the upload form.
    POST → save the file, create a DB record, kick off Celery task.
    """

    if request.method == "POST":
        # ── Validate form ─────────────────────────────────────────────────
        if "audio_file" not in request.files:
            flash("No file field in the form.", "danger")
            return redirect(request.url)

        file = request.files["audio_file"]

        if file.filename == "":
            flash("Please select a file before uploading.", "warning")
            return redirect(request.url)

        if not _allowed_file(file.filename):
            flash("Unsupported file type. Allowed: mp3, wav, flac, ogg, m4a, aiff", "danger")
            return redirect(request.url)

        # ── Save file with a UUID name to avoid collisions ────────────────
        from flask import current_app
        original_name = secure_filename(file.filename)
        ext           = original_name.rsplit(".", 1)[1].lower()
        stored_name   = f"{uuid.uuid4().hex}.{ext}"
        save_path     = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)
        file.save(save_path)

        # ── Create DB record ──────────────────────────────────────────────
        upload = Upload(
            user_id       = current_user.id,
            original_name = original_name,
            stored_name   = stored_name,
            status        = "pending",
        )
        db.session.add(upload)
        db.session.commit()

        # ── Dispatch background task ──────────────────────────────────────
        task = run_separation.delay(upload.id, save_path)
        upload.task_id = task.id
        db.session.commit()

        flash(f"'{original_name}' uploaded! Separation is in progress…", "info")
        return redirect(url_for("upload.status", upload_id=upload.id))

    return render_template("upload/upload.html")


# ── Job Status Page ───────────────────────────────────────────────────────────

@upload_bp.route("/status/<int:upload_id>")
@login_required
def status(upload_id: int):
    """
    Show a status page for a single job.
    The page uses JS polling (hitting /upload/api/status/<id>) to refresh.
    """

    upload = Upload.query.get_or_404(upload_id)

    # Security: only the owner can view their job
    if upload.user_id != current_user.id:
        abort(403)

    return render_template("upload/status.html", upload=upload)


# ── JSON Status API (polled by JS) ────────────────────────────────────────────

@upload_bp.route("/api/status/<int:upload_id>")
@login_required
def api_status(upload_id: int):
    """Returns job status as JSON for the polling script."""

    upload = Upload.query.get_or_404(upload_id)

    if upload.user_id != current_user.id:
        abort(403)

    return jsonify({
        "status":     upload.status,
        "download_url": url_for("upload.download", upload_id=upload.id)
                        if upload.status == "done" else None,
        "error":      upload.error_msg,
    })


# ── Download ──────────────────────────────────────────────────────────────────

@upload_bp.route("/download/<int:upload_id>")
@login_required
def download(upload_id: int):
    """Serve the finished stems ZIP file."""

    from flask import current_app

    upload = Upload.query.get_or_404(upload_id)

    if upload.user_id != current_user.id:
        abort(403)

    if upload.status != "done" or not upload.output_zip:
        flash("Stems are not ready yet.", "warning")
        return redirect(url_for("upload.status", upload_id=upload_id))

    return send_from_directory(
        current_app.config["OUTPUT_FOLDER"],
        upload.output_zip,
        as_attachment=True,
        download_name=f"stems_{upload.original_name}.zip",
    )


# ── History Page ──────────────────────────────────────────────────────────────

@upload_bp.route("/history")
@login_required
def history():
    """Show all jobs for the current user, newest first."""

    uploads = (Upload.query
               .filter_by(user_id=current_user.id)
               .order_by(Upload.created_at.desc())
               .all())
    return render_template("upload/history.html", uploads=uploads)
