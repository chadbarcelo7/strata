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