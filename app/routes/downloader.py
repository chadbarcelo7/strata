"""
app/routes/downloader.py
YouTube → MP3/WAV downloader using yt-dlp.

Install:
    pip install yt-dlp

Register in app/__init__.py:
    from app.routes.downloader import downloader_bp
    app.register_blueprint(downloader_bp)
"""

import os
import re
import sys
import uuid
import threading
import subprocess
import json

# Resolve yt-dlp from the same venv as the running Python
_YTDLP = os.path.join(os.path.dirname(sys.executable), 'yt-dlp.exe') \
    if os.name == 'nt' else os.path.join(os.path.dirname(sys.executable), 'yt-dlp')
if not os.path.exists(_YTDLP):
    _YTDLP = 'yt-dlp'  # fallback to PATH
from flask import (Blueprint, render_template, request,
                   jsonify, send_from_directory, abort, current_app)
from flask_login import login_required, current_user

downloader_bp = Blueprint('downloader', __name__, url_prefix='/downloader')

# In-memory job store  {job_id: {status, progress, filename, error, title}}
_jobs = {}
_jobs_lock = threading.Lock()


def _safe_filename(title: str) -> str:
    """Strip characters that are illegal in filenames."""
    title = re.sub(r'[\\/*?:"<>|]', '', title)
    title = re.sub(r'\s+', '_', title.strip())
    return title[:80] or 'audio'


def _download_thread(app, job_id: str, url: str, fmt: str):
    """Background thread: runs yt-dlp and updates job status."""
    with app.app_context():
        # Save downloads to ~/Downloads/Strata_Stem/download/
        strata_root = os.path.join(os.path.expanduser('~'), 'Downloads', 'Strata_Stem')
        out_dir = os.path.join(strata_root, 'download')
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs(os.path.join(strata_root, 'Stem_output'), exist_ok=True)

        uid       = uuid.uuid4().hex[:8]
        tmpl_base = os.path.join(out_dir, f'ytdl_{uid}_%(title)s')

        with _jobs_lock:
            _jobs[job_id]['status'] = 'downloading'

        try:
            # ── yt-dlp command ───────────────────────────────────────────
            if fmt == 'wav':
                # Best audio → WAV (lossless PCM)
                cmd = [
                    _YTDLP,
                    '--no-playlist',
                    '--extract-audio',
                    '--audio-format', 'wav',
                    '--audio-quality', '0',
                    '--output', tmpl_base + '.%(ext)s',
                    '--print-json',
                    '--no-simulate',
                    url,
                ]
            else:
                # Best audio → MP3 320kbps
                cmd = [
                    _YTDLP,
                    '--no-playlist',
                    '--extract-audio',
                    '--audio-format', 'mp3',
                    '--audio-quality', '0',
                    '--postprocessor-args', 'ffmpeg:-b:a 320k',
                    '--output', tmpl_base + '.%(ext)s',
                    '--print-json',
                    '--no-simulate',
                    url,
                ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,   # 10 min max
            )

            if result.returncode != 0:
                err = result.stderr[-600:] or result.stdout[-600:]
                raise RuntimeError(err)

            # yt-dlp prints JSON info on stdout (last non-empty line)
            info = {}
            for line in reversed(result.stdout.strip().splitlines()):
                line = line.strip()
                if line.startswith('{'):
                    try:
                        info = json.loads(line)
                        break
                    except Exception:
                        pass

            title    = info.get('title', 'audio')
            duration = info.get('duration_string', '')
            thumb    = info.get('thumbnail', '')

            # Find the output file
            ext      = 'wav' if fmt == 'wav' else 'mp3'
            safe     = _safe_filename(title)
            # yt-dlp uses the actual title in the filename
            candidates = [
                f for f in os.listdir(out_dir)
                if f.startswith(f'ytdl_{uid}_') and f.endswith(f'.{ext}')
            ]
            if not candidates:
                # fallback: any new file with our uid prefix
                candidates = [
                    f for f in os.listdir(out_dir)
                    if f.startswith(f'ytdl_{uid}_')
                ]
            if not candidates:
                raise RuntimeError('Download completed but output file not found.')

            filename  = candidates[0]
            file_path = os.path.join(out_dir, filename)

            with _jobs_lock:
                _jobs[job_id].update({
                    'status':    'done',
                    'filename':  filename,
                    'file_path': file_path,
                    'title':     title,
                    'duration':  duration,
                    'thumb':    thumb,
                    'format':   fmt,
                    'error':    None,
                })

        except subprocess.TimeoutExpired:
            with _jobs_lock:
                _jobs[job_id].update({'status': 'error', 'error': 'Download timed out (10 min limit).'})
        except Exception as exc:
            with _jobs_lock:
                _jobs[job_id].update({'status': 'error', 'error': str(exc)[:400]})


# ── Routes ────────────────────────────────────────────────────────────────────

@downloader_bp.route('/')
@login_required
def index():
    return render_template('downloader/index.html')


@downloader_bp.route('/start', methods=['POST'])
@login_required
def start():
    """POST {url, format} → {job_id}"""
    body = request.get_json(force=True) or {}
    url  = (body.get('url') or '').strip()
    fmt  = body.get('format', 'mp3').lower()

    if not url:
        return jsonify(error='No URL provided'), 400
    if fmt not in ('mp3', 'wav'):
        fmt = 'mp3'

    # Basic URL validation
    if not re.match(r'https?://', url):
        return jsonify(error='Invalid URL — must start with http:// or https://'), 400
    if not any(d in url for d in ('youtube.com', 'youtu.be')):
        return jsonify(error='Only YouTube URLs are supported'), 400

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            'status':   'queued',
            'filename': None,
            'title':    None,
            'duration': None,
            'thumb':    None,
            'format':   fmt,
            'error':    None,
        }

    app = current_app._get_current_object()
    t   = threading.Thread(
        target=_download_thread,
        args=(app, job_id, url, fmt),
        daemon=True,
    )
    t.start()

    return jsonify(job_id=job_id)


@downloader_bp.route('/status/<job_id>')
@login_required
def job_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify(error='Job not found'), 404
    return jsonify(job)


@downloader_bp.route('/file/<job_id>')
@login_required
def get_file(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or job['status'] != 'done' or not job['filename']:
        abort(404)

    out_dir  = current_app.config['OUTPUT_FOLDER']
    filename = job['filename']
    title    = job.get('title', 'audio')
    fmt      = job.get('format', 'mp3')
    ext      = 'wav' if fmt == 'wav' else 'mp3'
    safe     = _safe_filename(title) + '.' + ext

    return send_from_directory(out_dir, filename,
                               as_attachment=True,
                               download_name=safe)
