# fix_structure.ps1
# Run this from C:\Users\chadb\Desktop\musica-stem
# It creates the correct folder layout and moves all files into place.

$root = "C:\Users\chadb\Desktop\musica-stem"
Set-Location $root

# ── Create all required folders ───────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path "app"
New-Item -ItemType Directory -Force -Path "app\routes"
New-Item -ItemType Directory -Force -Path "app\services"
New-Item -ItemType Directory -Force -Path "app\models"
New-Item -ItemType Directory -Force -Path "app\templates\auth"
New-Item -ItemType Directory -Force -Path "app\templates\main"
New-Item -ItemType Directory -Force -Path "app\templates\upload"
New-Item -ItemType Directory -Force -Path "app\static\uploads"
New-Item -ItemType Directory -Force -Path "app\static\outputs"

# ── Move Python source files ───────────────────────────────────────────────────
Move-Item -Force ".\__init__.py"        "app\__init__.py"
Move-Item -Force ".\auth.py"            "app\routes\auth.py"
Move-Item -Force ".\main.py"            "app\routes\main.py"
Move-Item -Force ".\upload.py"          "app\routes\upload.py"
Move-Item -Force ".\audio_service.py"   "app\services\audio_service.py"
Move-Item -Force ".\tasks.py"           "app\services\tasks.py"
Move-Item -Force ".\user.py"            "app\models\user.py"

# ── Move HTML templates ────────────────────────────────────────────────────────
Move-Item -Force ".\base.html"          "app\templates\base.html"
Move-Item -Force ".\index.html"         "app\templates\main\index.html"
Move-Item -Force ".\login.html"         "app\templates\auth\login.html"
Move-Item -Force ".\register.html"      "app\templates\auth\register.html"
Move-Item -Force ".\upload.html"        "app\templates\upload\upload.html"
Move-Item -Force ".\status.html"        "app\templates\upload\status.html"
Move-Item -Force ".\history.html"       "app\templates\upload\history.html"

# ── Create missing __init__.py files for sub-packages ─────────────────────────
"" | Out-File -Encoding utf8 "app\routes\__init__.py"
"" | Out-File -Encoding utf8 "app\services\__init__.py"
"" | Out-File -Encoding utf8 "app\models\__init__.py"

# ── Create missing upload.py model (was never in the flat dump) ───────────────
@'
from app import db

class Upload(db.Model):
    __tablename__ = "uploads"
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name   = db.Column(db.String(255), nullable=False)
    status        = db.Column(db.String(20), default="pending", nullable=False)
    task_id       = db.Column(db.String(155), nullable=True)
    output_zip    = db.Column(db.String(255), nullable=True)
    error_msg     = db.Column(db.Text, nullable=True)
    created_at    = db.Column(db.DateTime, server_default=db.func.now())
    updated_at    = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
'@ | Out-File -Encoding utf8 "app\models\upload.py"

# ── Print final structure ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "Done! Final structure:" -ForegroundColor Green
Get-ChildItem -Recurse -Name | Where-Object { $_ -notmatch "__pycache__" }
