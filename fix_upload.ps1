# fix_upload.ps1
# Run from C:\Users\chadb\Desktop\musica-stem
# Rewrites app\routes\upload.py and app\models\upload.py with correct content

$root = "C:\Users\chadb\Desktop\musica-stem"
Set-Location $root

# ── app\routes\upload.py (the Blueprint with upload_bp) ───────────────────────
@'
import os
import uuid
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, jsonify, send_from_directory, abort,
                   current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.upload import Upload
from app.services.tasks import run_separation

upload_bp = Blueprint("upload", __name__, url_prefix="/upload")


def _allowed_file(filename):
    allowed = current_app.config["ALLOWED_EXTENSIONS"]
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


@upload_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
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
        original_name = secure_filename(file.filename)
        ext           = original_name.rsplit(".", 1)[1].lower()
        stored_name   = f"{uuid.uuid4().hex}.{ext}"
        save_path     = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)
        file.save(save_path)
        upload = Upload(
            user_id=current_user.id,
            original_name=original_name,
            stored_name=stored_name,
            status="pending",
        )
        db.session.add(upload)
        db.session.commit()
        task = run_separation.delay(upload.id, save_path)
        upload.task_id = task.id
        db.session.commit()
        flash(f"'{original_name}' uploaded! Separation is in progress.", "info")
        return redirect(url_for("upload.status", upload_id=upload.id))
    return render_template("upload/upload.html")


@upload_bp.route("/status/<int:upload_id>")
@login_required
def status(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    if upload.user_id != current_user.id:
        abort(403)
    return render_template("upload/status.html", upload=upload)


@upload_bp.route("/api/status/<int:upload_id>")
@login_required
def api_status(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    if upload.user_id != current_user.id:
        abort(403)
    return jsonify({
        "status": upload.status,
        "download_url": url_for("upload.download", upload_id=upload.id)
                        if upload.status == "done" else None,
        "error": upload.error_msg,
    })


@upload_bp.route("/download/<int:upload_id>")
@login_required
def download(upload_id):
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


@upload_bp.route("/history")
@login_required
def history():
    uploads = (Upload.query
               .filter_by(user_id=current_user.id)
               .order_by(Upload.created_at.desc())
               .all())
    return render_template("upload/history.html", uploads=uploads)
'@ | Out-File -Encoding utf8 "app\routes\upload.py"

Write-Host "app\routes\upload.py written." -ForegroundColor Green

# ── app\models\upload.py (the ORM model) ──────────────────────────────────────
@'
from app import db

class Upload(db.Model):
    __tablename__ = "uploads"
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name   = db.Column(db.String(255), nullable=False)
    status        = db.Column(db.String(20),  default="pending", nullable=False)
    task_id       = db.Column(db.String(155), nullable=True)
    output_zip    = db.Column(db.String(255), nullable=True)
    error_msg     = db.Column(db.Text,        nullable=True)
    created_at    = db.Column(db.DateTime,    server_default=db.func.now())
    updated_at    = db.Column(db.DateTime,    server_default=db.func.now(),
                              onupdate=db.func.now())
'@ | Out-File -Encoding utf8 "app\models\upload.py"

Write-Host "app\models\upload.py written." -ForegroundColor Green

# ── app\models\__init__.py ─────────────────────────────────────────────────────
@'
from app.models.user import User
from app.models.upload import Upload
'@ | Out-File -Encoding utf8 "app\models\__init__.py"

Write-Host "app\models\__init__.py written." -ForegroundColor Green
Write-Host ""
Write-Host "All done. Now run: python run.py" -ForegroundColor Cyan
