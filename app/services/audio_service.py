"""
app/services/audio_service.py
Handles Demucs separation + second-pass guitar/synth split + tempo/key analysis.

Pipeline:
  Pass 1 — htdemucs_6s  →  vocals, drums, bass, guitar, piano, other
  Pass 2 — htdemucs_6s on other.wav  →  extracts guitar-like content
            Produces:  other_guitar.wav  (guitar/synth-like from "other")
                       other_synth.wav   (remainder: pads, ambience, FX)
"""

import os
import sys
import shutil
import zipfile
import subprocess
import logging
import json
import tempfile
from pathlib import Path
from flask import current_app

logger = logging.getLogger(__name__)


# ── Key detection helpers ──────────────────────────────────────────────────────
_NOTES   = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
_MAJOR_P = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_P = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def _correlate(chroma, profile):
    import numpy as np
    chroma  = np.array(chroma)
    profile = np.array(profile)
    scores  = []
    for shift in range(len(chroma)):
        rolled = np.roll(chroma, -shift)
        corr   = np.corrcoef(rolled, profile)[0, 1]
        scores.append(corr if not np.isnan(corr) else -1)
    return scores


def detect_key(audio_path: str) -> dict:
    """Returns {'key': 'C Major', 'confidence': 0.82}"""
    try:
        import librosa
        import numpy as np
        y, sr        = librosa.load(audio_path, mono=True, duration=60)
        chroma       = librosa.feature.chroma_cqt(y=y, sr=sr)
        mean_chroma  = chroma.mean(axis=1).tolist()
        major_scores = _correlate(mean_chroma, _MAJOR_P)
        minor_scores = _correlate(mean_chroma, _MINOR_P)
        best_major   = max(range(12), key=lambda i: major_scores[i])
        best_minor   = max(range(12), key=lambda i: minor_scores[i])
        if major_scores[best_major] >= minor_scores[best_minor]:
            key        = _NOTES[best_major] + ' Major'
            confidence = round(float(major_scores[best_major]), 3)
        else:
            key        = _NOTES[best_minor] + ' Minor'
            confidence = round(float(minor_scores[best_minor]), 3)
        return {'key': key, 'confidence': max(0.0, confidence)}
    except Exception as e:
        logger.warning("Key detection failed: %s", e)
        return {'key': 'Unknown', 'confidence': 0.0}


def detect_tempo(audio_path: str) -> dict:
    """Returns {'bpm': 120.5}"""
    try:
        import librosa
        y, sr  = librosa.load(audio_path, mono=True, duration=60)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo.flat[0]) if hasattr(tempo, 'flat') else float(tempo)
        return {'bpm': round(bpm, 1)}
    except Exception as e:
        logger.warning("Tempo detection failed: %s", e)
        return {'bpm': 0.0}


# ── Demucs runner ──────────────────────────────────────────────────────────────
def _run_demucs(model: str, input_path: str, output_dir: str,
                timeout: int = 7200) -> list:
    """
    Run Demucs on input_path, writing stems to output_dir.
    Returns list of Path objects for the produced .wav files.
    Raises RuntimeError on failure.
    """
    result = subprocess.run(
        [
            sys.executable, '-m', 'demucs',
            '--name', model,
            '--out',  str(Path(output_dir).resolve()),
            str(Path(input_path).resolve()),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        logger.error("Demucs stderr:\n%s", result.stderr)
        raise RuntimeError(
            f'Demucs ({model}) failed (exit {result.returncode}).\n'
            f'{result.stderr[-600:] or result.stdout[-600:]}'
        )
    stems = list(Path(output_dir).rglob('*.wav'))
    if not stems:
        raise RuntimeError(
            f'Demucs ({model}) produced no .wav files. '
            f'stdout: {result.stdout[-300:]}'
        )
    return stems


# ── Second-pass: split "other" into guitar-like vs synth/pad ──────────────────
def _second_pass_other(other_wav: Path, pass2_dir: str) -> dict:
    """
    Re-run htdemucs_6s on other.wav.
    The 'guitar' output of this second pass becomes other_guitar.wav
    The sum of everything else becomes other_synth.wav (piano + other residual).

    Returns {'other_guitar': Path, 'other_synth': Path} or {} on failure.
    """
    try:
        import numpy as np
        from scipy.io import wavfile
    except ImportError:
        logger.warning("numpy/scipy not available for second-pass mixing — skipping")
        return {}

    logger.info("Second pass: separating other.wav → guitar + synth")
    os.makedirs(pass2_dir, exist_ok=True)

    try:
        pass2_stems = _run_demucs(
            model      = 'htdemucs_6s',
            input_path = str(other_wav),
            output_dir = pass2_dir,
            timeout    = 3600,
        )
    except RuntimeError as e:
        logger.warning("Second pass failed: %s", e)
        return {}

    # Index the second-pass stems by name
    stem_map = {s.name: s for s in pass2_stems}
    logger.info("Second-pass stems: %s", list(stem_map.keys()))

    # Guitar stem from second pass → other_guitar.wav
    guitar_src = stem_map.get('guitar.wav')
    if not guitar_src:
        logger.warning("No guitar.wav in second pass output")
        return {}

    # Synth = piano.wav + other.wav from second pass (pads, FX, ambient)
    # We mix them together with scipy to produce other_synth.wav
    synth_sources = [s for n, s in stem_map.items()
                     if n in ('piano.wav', 'other.wav')]

    results = {}
    out_dir = Path(pass2_dir)

    # Copy guitar stem
    other_guitar_path = out_dir / 'other_guitar.wav'
    shutil.copy2(str(guitar_src), str(other_guitar_path))
    results['other_guitar'] = other_guitar_path

    # Mix synth sources
    if synth_sources:
        try:
            mixed = None
            sr    = None
            for src in synth_sources:
                rate, data = wavfile.read(str(src))
                data = data.astype(np.float32)
                if mixed is None:
                    mixed = data
                    sr    = rate
                else:
                    # Pad/trim to same length before summing
                    if data.shape[0] > mixed.shape[0]:
                        data = data[:mixed.shape[0]]
                    elif data.shape[0] < mixed.shape[0]:
                        pad = np.zeros((mixed.shape[0] - data.shape[0],) + data.shape[1:],
                                       dtype=np.float32)
                        data = np.vstack([data, pad]) if data.ndim > 1 else np.concatenate([data, pad])
                    mixed = mixed + data

            # Normalise to prevent clipping (keep as int16)
            peak = np.abs(mixed).max()
            if peak > 0:
                mixed = mixed / peak * 32000
            mixed = mixed.astype(np.int16)

            other_synth_path = out_dir / 'other_synth.wav'
            wavfile.write(str(other_synth_path), sr, mixed)
            results['other_synth'] = other_synth_path
            logger.info("other_synth.wav written (%d samples)", mixed.shape[0])
        except Exception as e:
            logger.warning("Synth mix failed: %s", e)

    return results


# ── Main entry point ───────────────────────────────────────────────────────────
def separate_audio(input_path: str, job_id: int) -> str:

    output_dir     = current_app.config['OUTPUT_FOLDER']
    model          = current_app.config.get('DEMUCS_MODEL', 'htdemucs_6s')
    job_output_dir = os.path.join(output_dir, f'job_{job_id}')
    pass2_dir      = os.path.join(output_dir, f'job_{job_id}_pass2')
    os.makedirs(job_output_dir, exist_ok=True)

    input_path_str = str(Path(input_path).resolve())
    logger.info("Pass 1 — model=%s  file=%s", model, input_path_str)

    # ── Pass 1: full song separation ──────────────────────────────────────
    try:
        stem_files = _run_demucs(model, input_path_str, job_output_dir)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Demucs timed out after 2 hours.')
    except FileNotFoundError:
        raise RuntimeError(f'Could not launch Python at: {sys.executable}')

    logger.info("Pass 1 stems: %s", [f.name for f in stem_files])

    # ── Pass 2: re-separate the "other" stem ──────────────────────────────
    other_wav = next((f for f in stem_files if f.name == 'other.wav'), None)
    pass2_results = {}

    if other_wav:
        pass2_results = _second_pass_other(other_wav, pass2_dir)
        if pass2_results:
            logger.info("Pass 2 produced: %s", [p.name for p in pass2_results.values()])
        else:
            logger.info("Pass 2 skipped or failed — keeping original other.wav")
    else:
        logger.warning("No other.wav found in pass 1 output")

    # ── Tempo + key analysis ──────────────────────────────────────────────
    try:
        tempo_data = detect_tempo(input_path_str)
        key_data   = detect_key(input_path_str)
        analysis   = {
            'bpm':        tempo_data['bpm'],
            'key':        key_data['key'],
            'confidence': key_data['confidence'],
        }
        logger.info("Analysis: %s", analysis)
    except Exception as e:
        logger.warning("Analysis skipped: %s", e)
        analysis = {'bpm': 0.0, 'key': 'Unknown', 'confidence': 0.0}

    # ── Build ZIP ─────────────────────────────────────────────────────────
    zip_name = f'stems_job_{job_id}.zip'
    zip_path = os.path.join(output_dir, zip_name)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Pass 1 stems (vocals, drums, bass, guitar, piano, other)
        for stem_file in stem_files:
            zf.write(stem_file, arcname=stem_file.name)

        # Pass 2 extra stems (other_guitar, other_synth) if produced
        for name, path in pass2_results.items():
            zf.write(str(path), arcname=path.name)

        # Analysis metadata
        zf.writestr('analysis.json', json.dumps(analysis, indent=2))

    logger.info("ZIP created: %s", zip_path)

    # Cleanup temp dirs
    shutil.rmtree(job_output_dir, ignore_errors=True)
    shutil.rmtree(pass2_dir, ignore_errors=True)

    return zip_path


def get_analysis_from_zip(zip_path: str) -> dict:
    """Read analysis.json from the ZIP. Returns empty dict if not present."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if 'analysis.json' in zf.namelist():
                return json.loads(zf.read('analysis.json'))
    except Exception:
        pass
    return {}
