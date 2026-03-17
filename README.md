# 🎵 StemSplit — Flask Audio Stem Separation App

Upload any song → AI separates it into **vocals, drums, bass, other** → download as ZIP.

Built with **Flask + MySQL + Demucs + Celery**.

---

## 📁 Project Structure

```
audio_stems_app/
├── run.py                   # Entry point (Flask dev server + Celery reference)
├── config.py                # All configuration (loaded from .env)
├── schema.sql               # MySQL schema (run once)
├── requirements.txt         # Python dependencies
├── .env.example             # Copy → .env and fill in your values
│
└── app/
    ├── __init__.py          # Application factory (create_app)
    ├── models/
    │   ├── user.py          # User ORM model + Flask-Login integration
    │   └── upload.py        # Upload/job ORM model
    ├── routes/
    │   ├── auth.py          # /auth/register, /auth/login, /auth/logout
    │   ├── main.py          # / (landing page)
    │   └── upload.py        # /upload/ + /upload/status + /upload/download
    ├── services/
    │   ├── audio_service.py # Demucs wrapper (runs separation, zips output)
    │   └── tasks.py         # Celery task: run_separation
    ├── static/
    │   ├── uploads/         # Temporary uploaded audio files
    │   └── outputs/         # Finished stem ZIPs
    └── templates/
        ├── base.html        # Bootstrap 5 layout + navbar
        ├── main/index.html  # Landing page
        ├── auth/login.html
        ├── auth/register.html
        └── upload/
            ├── upload.html  # Drag-and-drop upload form
            ├── status.html  # Polling status page
            └── history.html # User's job history
```

---

## ⚙️ Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.10+ | python.org |
| MySQL | 8.0+ | dev.mysql.com |
| Redis | 7.0+ | redis.io (needed for Celery) |
| pip | latest | `pip install --upgrade pip` |

---

## 🚀 Setup Instructions

### 1. Clone / Copy the Project

```bash
cd audio_stems_app
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate         # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> **GPU acceleration (optional but recommended for speed):**
> If you have an NVIDIA GPU with CUDA:
> ```bash
> pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
> ```

### 4. Set Up MySQL

```sql
-- In MySQL client (mysql -u root -p):
CREATE DATABASE audio_stems;
```

Then run the schema:

```bash
mysql -u root -p audio_stems < schema.sql
```

### 5. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your MySQL credentials and a strong `SECRET_KEY`:

```ini
SECRET_KEY=your-super-secret-random-string-here
DB_USER=root
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_NAME=audio_stems
DEMUCS_MODEL=htdemucs
```

### 6. Start Redis (for Celery)

```bash
# macOS (Homebrew)
brew services start redis

# Linux
sudo systemctl start redis

# Docker (easiest)
docker run -d -p 6379:6379 redis:7
```

### 7. Start the Celery Worker (in a separate terminal)

```bash
source venv/bin/activate
celery -A run.celery worker --loglevel=info --concurrency=2
```

> `--concurrency=2` means 2 jobs can run in parallel.
> Reduce to 1 if RAM is limited (Demucs uses ~4 GB per job).

### 8. Run the Flask App

```bash
python run.py
```

Open: **http://localhost:5000**

---

## 🎛️ Demucs Models

Change `DEMUCS_MODEL` in `.env`:

| Model | Speed | Quality | Stems |
|-------|-------|---------|-------|
| `htdemucs` | Fast | ⭐⭐⭐⭐ | drums, bass, other, vocals |
| `htdemucs_ft` | Slow | ⭐⭐⭐⭐⭐ | drums, bass, other, vocals |
| `mdx_extra` | Medium | ⭐⭐⭐⭐ | drums, bass, other, vocals |

First run downloads the model weights (~1 GB) automatically.

---

## 🔄 How It Works

```
User uploads MP3
      │
      ▼
Flask saves file to static/uploads/<uuid>.mp3
Creates Upload record in MySQL (status=pending)
      │
      ▼
Celery task dispatched → status=processing
      │
      ▼
Demucs runs:
  python -m demucs --name htdemucs --out <output_dir> <input_file>
  → produces: drums.wav, bass.wav, other.wav, vocals.wav
      │
      ▼
Service zips stems → static/outputs/stems_job_<id>.zip
Upload record updated → status=done
      │
      ▼
Browser polls /upload/api/status/<id> every 4s
When done → shows Download button
```

---

## 🛡️ Security Notes

- Passwords are hashed with Werkzeug's `generate_password_hash` (PBKDF2-SHA256).
- Files are stored with UUID names (not user-provided names) to prevent path traversal.
- `secure_filename()` sanitises the original filename before any use.
- Users can only download their own jobs (owner check in routes).
- Set a strong `SECRET_KEY` before deploying.

---

## 🐳 Optional: Docker Compose

```yaml
# docker-compose.yml (add this file if you want containers)
version: '3.9'
services:
  db:
    image: mysql:8
    environment:
      MYSQL_ROOT_PASSWORD: secret
      MYSQL_DATABASE: audio_stems
    ports: ["3306:3306"]

  redis:
    image: redis:7
    ports: ["6379:6379"]

  web:
    build: .
    command: python run.py
    ports: ["5000:5000"]
    env_file: .env
    depends_on: [db, redis]

  worker:
    build: .
    command: celery -A run.celery worker --loglevel=info
    env_file: .env
    depends_on: [db, redis]
```

---

## ✨ Possible Enhancements

- **Email verification** on registration (Flask-Mail)
- **Rate limiting** per user (Flask-Limiter)
- **Two-stem mode** (vocals vs. instrumental only): add `--two-stems vocals` to Demucs command
- **Progress bar** using Celery's `update_state()` and a `/progress` SSE endpoint
- **Auto-delete** old files with a cron/scheduled Celery beat task
- **S3 storage** instead of local disk (boto3 + Flask-S3)
- **Stripe payments** for premium processing priority
