import io
import json
import math
import os
import subprocess
import tempfile
import threading
import uuid
import zipfile

from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, jsonify, send_from_directory,
                   send_file, abort, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models.upload import Upload

upload_bp = Blueprint('upload', __name__, url_prefix='/upload')

# Allowed stem filenames (4-stem, 6-stem, and second-pass split stems)
ALLOWED_STEMS = {
    'vocals.wav', 'drums.wav', 'bass.wav',
    'other.wav', 'guitar.wav', 'piano.wav',
    'other_guitar.wav', 'other_synth.wav',
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _allowed_file(filename):
    allowed = current_app.config['ALLOWED_EXTENSIONS']
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def _get_stem_cache_dir(upload_id):
    return os.path.join(current_app.config['OUTPUT_FOLDER'], f'stems_cache_{upload_id}')


def _extract_stems(upload):
    """Extract all WAV stems + analysis.json from ZIP into cache dir."""
    zip_path = os.path.join(current_app.config['OUTPUT_FOLDER'], upload.output_zip)
    if not os.path.exists(zip_path):
        return []

    cache_dir = _get_stem_cache_dir(upload.id)
    os.makedirs(cache_dir, exist_ok=True)

    extracted = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in zf.namelist():
            basename = os.path.basename(name)
            if basename in ALLOWED_STEMS or basename == 'analysis.json':
                dest = os.path.join(cache_dir, basename)
                if not os.path.exists(dest):
                    data = zf.read(name)
                    with open(dest, 'wb') as f:
                        f.write(data)
                if basename in ALLOWED_STEMS:
                    extracted.append(basename)
    return sorted(extracted)


def _build_atempo(rate: float) -> str:
    """
    Build a chained ffmpeg atempo filter string.
    atempo only accepts values in [0.5, 2.0] per node, so we chain for
    values outside that range.
    Example: rate=4.0  →  'atempo=2.0,atempo=2.0'
    """
    filters = []
    r = float(rate)
    while r > 2.0:
        filters.append('atempo=2.0')
        r /= 2.0
    while r < 0.5:
        filters.append('atempo=0.5')
        r *= 2.0
    filters.append(f'atempo={r:.8f}')
    return ','.join(filters)


def _run_separation_thread(app, upload_id, input_path):
    with app.app_context():
        upload = db.session.get(Upload, upload_id)
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


# ── Routes ────────────────────────────────────────────────────────────────────

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

    stem_list = []
    analysis  = {}

    if upload.status == 'done' and upload.output_zip:
        stem_list = _extract_stems(upload)
        cache_dir = _get_stem_cache_dir(upload_id)
        analysis_path = os.path.join(cache_dir, 'analysis.json')
        if os.path.exists(analysis_path):
            with open(analysis_path) as f:
                analysis = json.load(f)

    return render_template('upload/status.html',
                           upload=upload,
                           stem_list=stem_list,
                           analysis=analysis)


@upload_bp.route('/api/status/<int:upload_id>')
@login_required
def api_status(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    if upload.user_id != current_user.id:
        abort(403)
    return jsonify({
        'status':       upload.status,
        'download_url': url_for('upload.download', upload_id=upload.id)
                        if upload.status == 'done' else None,
        'error':        upload.error_msg,
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
    """Serve individual stem WAV for the browser mixer."""
    upload = Upload.query.get_or_404(upload_id)
    if upload.user_id != current_user.id:
        abort(403)
    if upload.status != 'done' or not upload.output_zip:
        abort(404)
    if stem_name not in ALLOWED_STEMS:
        abort(404)

    cache_dir = _get_stem_cache_dir(upload_id)
    stem_path = os.path.join(cache_dir, stem_name)

    if not os.path.exists(stem_path):
        _extract_stems(upload)
    if not os.path.exists(stem_path):
        abort(404)

    return send_from_directory(cache_dir, stem_name, mimetype='audio/wav')


@upload_bp.route('/stem/<int:upload_id>/<stem_name>/download')
@login_required
def stem_download(upload_id, stem_name):
    """Download a single stem WAV as an attachment."""
    upload = Upload.query.get_or_404(upload_id)
    if upload.user_id != current_user.id:
        abort(403)
    if upload.status != 'done' or not upload.output_zip:
        abort(404)
    if stem_name not in ALLOWED_STEMS:
        abort(404)

    cache_dir = _get_stem_cache_dir(upload_id)
    stem_path = os.path.join(cache_dir, stem_name)

    if not os.path.exists(stem_path):
        _extract_stems(upload)
    if not os.path.exists(stem_path):
        abort(404)

    base          = os.path.splitext(upload.original_name)[0]
    stem_label    = os.path.splitext(stem_name)[0]
    download_name = f'{base}_{stem_label}.wav'

    return send_from_directory(cache_dir, stem_name,
                               as_attachment=True,
                               download_name=download_name)


@upload_bp.route('/history')
@login_required
def history():
    uploads = (Upload.query
               .filter_by(user_id=current_user.id)
               .order_by(Upload.created_at.desc())
               .all())
    return render_template('upload/history.html', uploads=uploads)


@upload_bp.route('/export/<int:upload_id>', methods=['POST'])
@login_required
def export_mix(upload_id):
    """
    POST JSON body:
    {
      "format": "wav" | "mp3",
      "stems": {
        "vocals": { "volume": 1.0, "muted": false },
        "drums":  { "volume": 0.8, "muted": false },
        ...
      },
      "pitch": 0,     // semitones  (-12 to +12)
      "tempo": 100    // percent    (50 to 200, 100 = original)
    }

    Returns a WAV (lossless 16-bit 44.1kHz) or MP3 (320kbps) file download.
    """
    upload = Upload.query.get_or_404(upload_id)
    if upload.user_id != current_user.id:
        abort(403)
    if upload.status != 'done' or not upload.output_zip:
        abort(400)

    try:
        from pydub import AudioSegment
        from pydub.effects import normalize as pydub_normalize
    except ImportError:
        return jsonify(error='pydub not installed. Run: pip install pydub'), 500

    # Tell pydub exactly where ffmpeg is
    ffmpeg_path = current_app.config.get('FFMPEG_PATH', 'ffmpeg')
    AudioSegment.converter = ffmpeg_path
    AudioSegment.ffmpeg    = ffmpeg_path
    AudioSegment.ffprobe   = ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe').replace('ffmpeg', 'ffprobe')

    body       = request.get_json(force=True) or {}
    fmt        = body.get('format', 'wav').lower()
    stem_cfg   = body.get('stems', {})
    pitch_semi = float(body.get('pitch', 0))
    tempo_pct  = float(body.get('tempo', 100))

    if fmt not in ('wav', 'mp3'):
        return jsonify(error='format must be wav or mp3'), 400

    # ── Extract stems from ZIP into cache ─────────────────────────────────
    zip_path  = os.path.join(current_app.config['OUTPUT_FOLDER'], upload.output_zip)
    cache_dir = _get_stem_cache_dir(upload_id)
    os.makedirs(cache_dir, exist_ok=True)

    STEM_FILES = ['vocals.wav', 'drums.wav', 'bass.wav',
                  'guitar.wav', 'piano.wav', 'other.wav',
                  'other_guitar.wav', 'other_synth.wav']

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for entry in zf.namelist():
            bn   = os.path.basename(entry)
            dest = os.path.join(cache_dir, bn)
            if bn in STEM_FILES and not os.path.exists(dest):
                data = zf.read(entry)
                with open(dest, 'wb') as fh:
                    fh.write(data)

    # ── Mix stems together ────────────────────────────────────────────────
    # Bass gets +7dB server-side to match the browser 2.5× gain boost
    STEM_BOOSTS_DB = {'bass': 7.0}

    mix = None
    for stem_wav in STEM_FILES:
        key      = stem_wav.replace('.wav', '')
        wav_path = os.path.join(cache_dir, stem_wav)
        if not os.path.exists(wav_path):
            continue

        cfg = stem_cfg.get(key, {})
        if cfg.get('muted', False):
            continue   # skip muted stems entirely

        seg = AudioSegment.from_wav(wav_path)

        # Convert linear volume (0–1) to dB gain
        vol = max(0.001, float(cfg.get('volume', 1.0)))
        db  = 20.0 * math.log10(vol)
        db += STEM_BOOSTS_DB.get(key, 0.0)
        seg = seg + db   # pydub: + operator applies dB gain

        mix = seg if mix is None else mix.overlay(seg)

    if mix is None:
        return jsonify(error='All stems are muted — nothing to export.'), 400

    # ── Tempo change (pitch-preserving via ffmpeg atempo) ─────────────────
    if abs(tempo_pct - 100.0) > 0.5:
        rate    = tempo_pct / 100.0
        tmp_in  = tempfile.mktemp(suffix='.wav')
        tmp_out = tempfile.mktemp(suffix='.wav')
        try:
            mix.export(tmp_in, format='wav')
            subprocess.run(
                [ffmpeg_path, '-y', '-i', tmp_in,
                 '-filter:a', _build_atempo(rate), tmp_out],
                check=True, capture_output=True
            )
            mix = AudioSegment.from_wav(tmp_out)
        finally:
            for p in (tmp_in, tmp_out):
                try: os.unlink(p)
                except: pass

    # ── Pitch shift (tempo-preserving via asetrate + atempo + aresample) ──
    if abs(pitch_semi) > 0.01:
        orig_sr    = mix.frame_rate
        new_sr     = int(orig_sr * (2 ** (pitch_semi / 12.0)))
        rate_comp  = orig_sr / new_sr
        filt       = f'asetrate={new_sr},{_build_atempo(rate_comp)},aresample={orig_sr}'
        tmp_in     = tempfile.mktemp(suffix='.wav')
        tmp_out    = tempfile.mktemp(suffix='.wav')
        try:
            mix.export(tmp_in, format='wav')
            subprocess.run(
                [ffmpeg_path, '-y', '-i', tmp_in, '-filter:a', filt, tmp_out],
                check=True, capture_output=True
            )
            mix = AudioSegment.from_wav(tmp_out)
        finally:
            for p in (tmp_in, tmp_out):
                try: os.unlink(p)
                except: pass

    # ── Peak-normalize to −1 dBFS to prevent clipping ────────────────────
    mix = pydub_normalize(mix, headroom=1.0)

    # ── Render to in-memory buffer ────────────────────────────────────────
    buf  = io.BytesIO()
    base = os.path.splitext(upload.original_name)[0]

    if fmt == 'wav':
        mix = mix.set_frame_rate(44100).set_sample_width(2)   # 16-bit PCM 44.1kHz
        mix.export(buf, format='wav')
        filename = f'{base}_master.wav'
        mimetype = 'audio/wav'
    else:
        mix.export(buf, format='mp3', bitrate='320k',
                   tags={'title': base, 'artist': 'Groove Lab'})
        filename = f'{base}_master_320.mp3'
        mimetype = 'audio/mpeg'

    buf.seek(0)
    return send_file(buf, mimetype=mimetype,
                     as_attachment=True, download_name=filename)


# ── AI ANALYSIS ROUTE (Groq) ──────────────────────────────────────────────────
@upload_bp.route('/ai-analyze/<int:upload_id>', methods=['POST'])
@login_required
def ai_analyze(upload_id):
    """Proxy AI analysis through Groq API."""
    upload = Upload.query.filter_by(id=upload_id, user_id=current_user.id).first_or_404()

    data = request.get_json(force=True, silent=True) or {}
    prompt = data.get('prompt', '')

    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400

    api_key = current_app.config.get('GROQ_API_KEY', '') or os.environ.get('GROQ_API_KEY', '')

    if not api_key:
        return jsonify({'error': 'GROQ_API_KEY not configured. Add it to your .env file.'}), 503

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            max_tokens=1500,
            temperature=0.4,
            messages=[
                {
                    'role': 'system',
                    'content': 'You are an expert music producer and audio engineer. Always respond with valid JSON only — no markdown, no explanation, no code fences.'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ]
        )
        text = completion.choices[0].message.content
        return jsonify({'text': text})
    except ImportError:
        return jsonify({'error': 'groq package not installed. Run: pip install groq'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 502
