from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from env_loader import load_env_file

load_env_file()

from .auth import auth_bp

__all__ = ["auth_bp"]
