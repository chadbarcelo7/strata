import os
import uuid
import zipfile
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


@upload_bp.route('/stem/<int:upload_id>/<stem_name>')
@login_required
def stem_file(upload_id, stem_name):
    """Serve individual stem WAV files for the browser mixer."""
    upload = Upload.query.get_or_404(upload_id)
    if upload.user_id != current_user.id:
        abort(403)
    if upload.status != 'done' or not upload.output_zip:
        abort(404)

    # Validate stem name - only allow safe filenames
    allowed_stems = {'vocals.wav', 'drums.wav', 'bass.wav', 'other.wav'}
    if stem_name not in allowed_stems:
        abort(404)

    # Extract the requested stem from the ZIP into a temp location and serve it
    zip_path = os.path.join(current_app.config['OUTPUT_FOLDER'], upload.output_zip)
    if not os.path.exists(zip_path):
        abort(404)

    # Serve from a cached extracted folder
    stem_cache_dir = os.path.join(current_app.config['OUTPUT_FOLDER'], f'stems_cache_{upload_id}')
    stem_path = os.path.join(stem_cache_dir, stem_name)

    if not os.path.exists(stem_path):
        os.makedirs(stem_cache_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Find matching file in zip (may be nested)
            for name in zf.namelist():
                if os.path.basename(name) == stem_name:
                    data = zf.read(name)
                    with open(stem_path, 'wb') as f:
                        f.write(data)
                    break

    if not os.path.exists(stem_path):
        abort(404)

    return send_from_directory(stem_cache_dir, stem_name,
                               mimetype='audio/wav')


@upload_bp.route('/history')
@login_required
def history():
    uploads = (Upload.query
               .filter_by(user_id=current_user.id)
               .order_by(Upload.created_at.desc())
               .all())
    return render_template('upload/history.html', uploads=uploads)
