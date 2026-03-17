"""
app/services/audio_service.py
"""

import os
import sys
import shutil
import zipfile
import subprocess
import logging
from pathlib import Path
from flask import current_app

logger = logging.getLogger(__name__)


def separate_audio(input_path: str, job_id: int) -> str:

    # ── Try importing Demucs and give a helpful error if missing ─────────
    try:
        from demucs.separate import main as demucs_main
    except ImportError:
        raise RuntimeError(
            f"Demucs is not installed in the Python that is running this app.\n"
            f"Current Python: {sys.executable}\n"
            f"Fix: run this exact command:\n"
            f"  {sys.executable} -m pip install demucs --no-deps\n"
            f"  {sys.executable} -m pip install julius einops tqdm openunmix asteroid-filterbanks encodec\n"
            f"Then restart the app."
        )

    output_dir     = current_app.config["OUTPUT_FOLDER"]
    model          = current_app.config.get("DEMUCS_MODEL", "htdemucs")
    job_output_dir = os.path.join(output_dir, f"job_{job_id}")
    os.makedirs(job_output_dir, exist_ok=True)

    input_path_str     = str(Path(input_path).resolve())
    job_output_dir_str = str(Path(job_output_dir).resolve())

    logger.info("Starting Demucs. model=%s  file=%s", model, input_path_str)

    # ── Run Demucs via subprocess using the SAME Python that runs Flask ──
    # Using sys.executable guarantees we use the right interpreter/venv.
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "demucs",
                "--name", model,
                "--out",  job_output_dir_str,
                input_path_str,
            ],
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Demucs timed out after 1 hour.")

    if result.returncode != 0:
        logger.error("Demucs stderr:\n%s", result.stderr)
        raise RuntimeError(
            f"Demucs failed (exit code {result.returncode}).\n"
            f"stderr: {result.stderr[-800:]}"
        )

    logger.info("Demucs finished.")

    # ── Locate output stems ───────────────────────────────────────────────
    stem_files = list(Path(job_output_dir).rglob("*.wav"))
    if not stem_files:
        raise RuntimeError(
            "Demucs ran but produced no .wav files. "
            "Make sure ffmpeg is installed and the input file is a valid audio file."
        )

    logger.info("Found stems: %s", [f.name for f in stem_files])

    # ── Zip stems ─────────────────────────────────────────────────────────
    zip_name = f"stems_job_{job_id}.zip"
    zip_path = os.path.join(output_dir, zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for stem_file in stem_files:
            zf.write(stem_file, arcname=stem_file.name)

    logger.info("ZIP created: %s", zip_path)

    shutil.rmtree(job_output_dir, ignore_errors=True)

    return zip_path
