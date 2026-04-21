import os
from pathlib import Path
import sys

from flask import Flask

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from env_loader import load_env_file

load_env_file(_repo_root / "login-lab" / ".env")

from routes import auth_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(auth_bp)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
