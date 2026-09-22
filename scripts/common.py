import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def bootstrap():
    """Explicit import barrier so formatters keep app imports after path setup."""
    if str(ROOT / "backend") not in sys.path:
        sys.path.insert(0, str(ROOT / "backend"))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


bootstrap()


def load_core(env_file):
    from app.services.core import Core
    from app.settings import Settings

    core = Core(Settings.load(env_file))
    core.initialize()
    return core
