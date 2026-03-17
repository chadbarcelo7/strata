from app import db

class Upload(db.Model):
    __tablename__ = "uploads"
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name   = db.Column(db.String(255), nullable=False)
    status        = db.Column(db.String(20),  default="pending", nullable=False)
    task_id       = db.Column(db.String(155), nullable=True)
    output_zip    = db.Column(db.String(255), nullable=True)
    error_msg     = db.Column(db.Text,        nullable=True)
    created_at    = db.Column(db.DateTime,    server_default=db.func.now())
    updated_at    = db.Column(db.DateTime,    server_default=db.func.now(),
                              onupdate=db.func.now())
