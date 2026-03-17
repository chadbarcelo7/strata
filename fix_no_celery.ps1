# fix_no_celery.ps1
# Removes Celery/Redis and runs Demucs directly in Flask (no background worker needed)

$root = "C:\Users\chadb\Desktop\musica-stem"
Set-Location $root

# ── 1. New requirements.txt (no celery, no redis) ─────────────────────────────
$reqs = @"
Flask==3.0.3
Flask-Login==0.6.3
Flask-SQLAlchemy==3.1.1
Flask-WTF==1.2.1
WTForms==3.1.2
Werkzeug==3.0.3
SQLAlchemy==2.0.31
python-dotenv==1.0.1
"@
[System.IO.File]::WriteAllText("$root\requirements.txt", $reqs)
Write-Host "requirements.txt written (Celery removed)" -ForegroundColor Green

# ── 2. New app/__init__.py (no Celery) ────────────────────────────────────────
$init = @"
import os
import sys

_APP_DIR  = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_APP_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()


def create_app(env=None):
    from config import config_map
    app = Flask(__name__)

    env = env or os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config_map.get(env, config_map['development']))

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'

    from app.routes.auth   import auth_bp
    from app.routes.main   import main_bp
    from app.routes.upload import upload_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(upload_bp)

    return app
"@
[System.IO.File]::WriteAllText("$root\app\__init__.py", $init)
Write-Host "app/__init__.py written (no Celery)" -ForegroundColor Green

# ── 3. New app/routes/upload.py (runs separation synchronously) ───────────────
$upload_routes = @"
import os
import uuid
import threading
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, jsonify, send_from_directory, abort,
                   current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.upload import Upload

upload_bp = Blueprint('upload', __name__, url_prefix='/upload')


def _allowed_file(filename):
    allowed = current_app.config['ALLOWED_EXTENSIONS']
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def _run_separation_thread(app, upload_id, input_path):
    """Run Demucs in a background thread so the browser does not time out."""
    with app.app_context():
        upload = Upload.query.get(upload_id)
        if not upload:
            return
        upload.status = 'processing'
        db.session.commit()
        try:
            from app.services.audio_service import separate_audio
            zip_path = separate_audio(input_path, upload_id)
            upload.output_zip = os.path.basename(zip_path)
            upload.status = 'done'
        except Exception as exc:
            upload.status = 'error'
            upload.error_msg = str(exc)
        finally:
            db.session.commit()


@upload_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        if 'audio_file' not in request.files:
            flash('No file field in the form.', 'danger')
            return redirect(request.url)
        file = request.files['audio_file']
        if file.filename == '':
            flash('Please select a file before uploading.', 'warning')
            return redirect(request.url)
        if not _allowed_file(file.filename):
            flash('Unsupported file type. Allowed: mp3, wav, flac, ogg, m4a, aiff', 'danger')
            return redirect(request.url)

        original_name = secure_filename(file.filename)
        ext           = original_name.rsplit('.', 1)[1].lower()
        stored_name   = uuid.uuid4().hex + '.' + ext
        save_path     = os.path.join(current_app.config['UPLOAD_FOLDER'], stored_name)
        file.save(save_path)

        upload = Upload(
            user_id=current_user.id,
            original_name=original_name,
            stored_name=stored_name,
            status='pending',
        )
        db.session.add(upload)
        db.session.commit()

        # Fire separation in a daemon thread — no Redis/Celery needed
        app = current_app._get_current_object()
        t = threading.Thread(
            target=_run_separation_thread,
            args=(app, upload.id, save_path),
            daemon=True
        )
        t.start()

        flash(original_name + ' uploaded! Separation is in progress.', 'info')
        return redirect(url_for('upload.status', upload_id=upload.id))

    return render_template('upload/upload.html')


@upload_bp.route('/status/<int:upload_id>')
@login_required
def status(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    if upload.user_id != current_user.id:
        abort(403)
    return render_template('upload/status.html', upload=upload)


@upload_bp.route('/api/status/<int:upload_id>')
@login_required
def api_status(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    if upload.user_id != current_user.id:
        abort(403)
    return jsonify({
        'status': upload.status,
        'download_url': url_for('upload.download', upload_id=upload.id)
                        if upload.status == 'done' else None,
        'error': upload.error_msg,
    })


@upload_bp.route('/download/<int:upload_id>')
@login_required
def download(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    if upload.user_id != current_user.id:
        abort(403)
    if upload.status != 'done' or not upload.output_zip:
        flash('Stems are not ready yet.', 'warning')
        return redirect(url_for('upload.status', upload_id=upload_id))
    return send_from_directory(
        current_app.config['OUTPUT_FOLDER'],
        upload.output_zip,
        as_attachment=True,
        download_name='stems_' + upload.original_name + '.zip',
    )


@upload_bp.route('/history')
@login_required
def history():
    uploads = (Upload.query
               .filter_by(user_id=current_user.id)
               .order_by(Upload.created_at.desc())
               .all())
    return render_template('upload/history.html', uploads=uploads)
"@
[System.IO.File]::WriteAllText("$root\app\routes\upload.py", $upload_routes)
Write-Host "app/routes/upload.py written (threading, no Celery)" -ForegroundColor Green

# ── 4. Delete tasks.py (no longer needed) ─────────────────────────────────────
$tasksPath = "$root\app\services\tasks.py"
if (Test-Path $tasksPath) {
    Remove-Item $tasksPath
    Write-Host "app/services/tasks.py removed" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done! Now run:" -ForegroundColor Cyan
Write-Host "  pip install -r requirements.txt"
Write-Host "  python run.py"
