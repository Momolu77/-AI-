"""Each Playwright run creates a new isolated data directory and seed entries."""

import json
import logging
import os
import secrets
import sys
import tempfile
from pathlib import Path

from common import ROOT

run_dir = Path(tempfile.mkdtemp(prefix="e2e-", dir=ROOT / "artifacts"))
os.environ.update(
    APP_ENV="test",
    DATA_DIR=str(run_dir),
    DATABASE_URL=f"sqlite:///{run_dir / 'app.db'}",
    JWT_SECRET=secrets.token_urlsafe(48),
    AI_PROVIDER="fake",
    FAKE_AI_SCENARIO="success",
    AI_FIRST_TOKEN_TIMEOUT_SEC="2",
    AI_TOTAL_TIMEOUT_SEC="20",
)
from app.main import logger  # noqa: E402
from app.services.core import Core  # noqa: E402
from app.settings import Settings  # noqa: E402

logger.handlers = [logging.FileHandler(run_dir / "backend.log", encoding="utf-8")]

core = Core(Settings.load())
core.initialize()
tokens = core.seed()
(ROOT / "artifacts/e2e-current.json").write_text(
    json.dumps({"data_dir": str(run_dir), "tokens": tokens}), encoding="utf-8"
)
import uvicorn  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, log_level="warning", access_log=False)
