# 🪟 Windows Installation Guide for StemSplit

`lameenc` (a dependency of Demucs) has **no pre-built Windows wheel on PyPI**,
so a plain `pip install demucs` fails on Windows.
Follow the steps below exactly and it will work.

---

## Step 1 — Verify your Python version

Open a terminal (Command Prompt or PowerShell) and run:

```cmd
python --version
```

You need **Python 3.10, 3.11, or 3.12** (64-bit).
If you have 3.13+, downgrade — PyTorch wheels don't yet support it.

---

## Step 2 — Create and activate a virtual environment

```cmd
python -m venv venv
venv\Scripts\activate
```

Your prompt should now start with `(venv)`.

---

## Step 3 — Upgrade pip and install build tools

```cmd
python -m pip install --upgrade pip setuptools wheel
```

---

## Step 4 — Install PyTorch FIRST (before Demucs)

Choose ONE of the commands below based on your hardware:

### CPU only (works on any Windows PC):
```cmd
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### NVIDIA GPU (CUDA 11.8) — much faster separation:
```cmd
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### NVIDIA GPU (CUDA 12.1):
```cmd
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

> ℹ️ Check your CUDA version with: `nvidia-smi`

---

## Step 5 — Install lameenc from a pre-built wheel

`lameenc` is the problematic package. Install it via a trusted wheel source:

```cmd
pip install lameenc --only-binary=:all:
```

If that still fails, use the **conda** approach (most reliable on Windows):

```cmd
# Install Miniconda first from: https://docs.conda.io/en/latest/miniconda.html
conda install -c conda-forge lameenc
```

Or install it from the unofficial Windows wheels repository:
```cmd
pip install https://github.com/bastibe/python-soundfile/releases/download/0.12.1/soundfile-0.12.1-py3-none-any.whl
```

---

## Step 6 — Install Demucs WITHOUT its pip dependencies

```cmd
pip install demucs --no-deps
```

Then manually install Demucs' remaining dependencies (these all have Windows wheels):

```cmd
pip install julius einops tqdm openunmix asteroid-filterbanks diffq
pip install librosa soundfile
```

---

## Step 7 — Install the rest of the app dependencies

```cmd
pip install Flask==3.0.3 Flask-Login==0.6.3 Flask-SQLAlchemy==3.1.1
pip install Flask-WTF==1.2.1 WTForms==3.1.2 Werkzeug==3.0.3
pip install SQLAlchemy==2.0.31 PyMySQL==1.1.1 cryptography==43.0.0
pip install celery==5.4.0 redis==5.0.8 python-dotenv==1.0.1
```

---

## Step 8 — Verify Demucs works

```cmd
python -c "import demucs; print('Demucs OK')"
python -m demucs --help
```

You should see the Demucs help output with no errors.

---

## Alternative: Use Conda (Easiest on Windows)

If the above is too painful, use conda which handles binary deps automatically:

```cmd
conda create -n stemsplit python=3.11
conda activate stemsplit

conda install -c conda-forge pytorch torchaudio cpuonly -c pytorch
conda install -c conda-forge lameenc ffmpeg

pip install demucs --no-deps
pip install julius einops tqdm openunmix asteroid-filterbanks diffq
pip install Flask Flask-Login Flask-SQLAlchemy Flask-WTF Werkzeug
pip install SQLAlchemy PyMySQL cryptography celery redis python-dotenv
```

---

## Step 9 — Install Redis on Windows

Redis doesn't have an official Windows binary, but there are two easy options:

### Option A — WSL2 (recommended):
```bash
# In WSL2 terminal:
sudo apt install redis-server
sudo service redis-server start
```

### Option B — Docker Desktop:
```cmd
docker run -d -p 6379:6379 redis:7
```

### Option C — Windows port of Redis:
Download from: https://github.com/tporadowski/redis/releases
Run `redis-server.exe`

---

## Step 10 — Run the app (Windows)

Open **3 separate terminals**, all with `(venv)` activated:

**Terminal 1 — Flask:**
```cmd
venv\Scripts\activate
python run.py
```

**Terminal 2 — Celery Worker:**
```cmd
venv\Scripts\activate
celery -A run.celery worker --loglevel=info --pool=solo
```
> ⚠️ On Windows, Celery requires `--pool=solo` (default multiprocessing pool doesn't work on Windows).

**Terminal 3 — Redis** (if not using Docker):
```cmd
redis-server.exe
```

Then open http://localhost:5000

---

## Common Windows Errors & Fixes

| Error | Fix |
|-------|-----|
| `lameenc>=1.2 not found` | Use `--no-deps` + install lameenc via conda |
| `No module named 'demucs'` | Make sure venv is activated |
| `celery worker not starting` | Add `--pool=solo` to celery command |
| `redis.exceptions.ConnectionError` | Start Redis first (Docker or WSL2) |
| `Access denied for MySQL user` | Check `.env` DB_PASSWORD matches MySQL |
| `torch not found` | Install PyTorch BEFORE Demucs |
