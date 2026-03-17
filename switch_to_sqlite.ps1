# switch_to_sqlite.ps1
# Run from C:\Users\chadb\Desktop\musica-stem

$root = "C:\Users\chadb\Desktop\musica-stem"
Set-Location $root

# Write config.py
$config = @"
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "audio_stems.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads")
    OUTPUT_FOLDER = os.path.join(BASE_DIR, "app", "static", "outputs")
    ALLOWED_EXTENSIONS = {"mp3", "wav", "flac", "ogg", "m4a", "aiff"}
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    DEMUCS_MODEL = os.environ.get("DEMUCS_MODEL", "htdemucs")

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
"@
[System.IO.File]::WriteAllText("$root\config.py", $config)
Write-Host "config.py written" -ForegroundColor Green

# Write requirements.txt
$reqs = @"
Flask==3.0.3
Flask-Login==0.6.3
Flask-SQLAlchemy==3.1.1
Flask-WTF==1.2.1
WTForms==3.1.2
Werkzeug==3.0.3
SQLAlchemy==2.0.31
celery==5.4.0
redis==5.0.8
python-dotenv==1.0.1
"@
[System.IO.File]::WriteAllText("$root\requirements.txt", $reqs)
Write-Host "requirements.txt written" -ForegroundColor Green

# Write run.py
$runpy = @"
import sys
import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import create_app, db
from app.models.user import User
from app.models.upload import Upload

app = create_app(os.environ.get("FLASK_ENV", "development"))

with app.app_context():
    db.create_all()
    print("Database tables created/verified.")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
"@
[System.IO.File]::WriteAllText("$root\run.py", $runpy)
Write-Host "run.py written" -ForegroundColor Green

Write-Host ""
Write-Host "Done. Now run:" -ForegroundColor Cyan
Write-Host "  pip install -r requirements.txt"
Write-Host "  python run.py"
