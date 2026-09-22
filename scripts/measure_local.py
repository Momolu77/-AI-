"""Measure 30 samples against an isolated real loopback HTTP server."""

import argparse
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from common import ROOT, bootstrap

bootstrap()

from app.services.core import Core  # noqa: E402
from app.settings import Settings  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "artifacts/performance.json"))
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="performance-", dir=ROOT / "artifacts"))
    secret = secrets.token_urlsafe(48)
    settings = Settings(data_dir=root, database=root / "app.db", secret=secret, env="test")
    core = Core(settings)
    core.initialize()
    tokens = core.seed()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATA_DIR": str(root),
        "DATABASE_URL": f"sqlite:///{root / 'app.db'}",
        "JWT_SECRET": secret,
        "AI_PROVIDER": "fake",
    }
    logfile = (root / "server.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            "backend",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=ROOT,
        env=env,
        stdout=logfile,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            for _ in range(100):
                try:
                    client.get("/health").raise_for_status()
                    break
                except httpx.HTTPError:
                    time.sleep(0.1)
            info = client.post(
                "/api/v1/session/bootstrap", json={"seat": "01", "token": tokens["01"]}
            ).json()
            client.headers["Authorization"] = "Bearer " + info["token"]
            measurements = {"save_code_ms": [], "create_preview_ms": [], "event_batch_50_ms": []}
            content = "<!DOCTYPE html><p>performance</p><!--" + "a" * 100000 + "-->"
            for index in range(30):
                for name, method, path, body in [
                    (
                        "save_code_ms",
                        "PUT",
                        "/workbench/code",
                        {"content": content, "revision": index + 1},
                    ),
                    (
                        "create_preview_ms",
                        "POST",
                        "/workbench/preview/run",
                        {
                            "content": content,
                            "revision": index + 1,
                            "run_id": str(uuid.uuid4()),
                            "occurred_at": datetime.now(UTC).isoformat(),
                        },
                    ),
                    (
                        "event_batch_50_ms",
                        "POST",
                        "/events/batch",
                        {
                            "session_id": info["id"],
                            "events": [
                                {
                                    "event_id": str(uuid.uuid4()),
                                    "event_name": "planner_opened",
                                    "actor": "student",
                                    "occurred_at": datetime.now(UTC).isoformat(),
                                    "client_sequence_no": index * 50 + n + 1,
                                    "payload": {},
                                }
                                for n in range(50)
                            ],
                        },
                    ),
                ]:
                    start = time.perf_counter()
                    response = client.request(method, "/api/v1" + path, json=body)
                    elapsed = (time.perf_counter() - start) * 1000
                    response.raise_for_status()
                    if name == "event_batch_50_ms":
                        assert all(r["status"] == "accepted" for r in response.json()["results"])
                    measurements[name].append(round(elapsed, 3))
            results = {
                key: {
                    "samples": samples,
                    "count": len(samples),
                    "p95_ms": sorted(samples)[28],
                    "target_ms": 500 if key == "event_batch_50_ms" else 1000,
                }
                for key, samples in measurements.items()
            }
            for item in results.values():
                item["within_target"] = item["p95_ms"] <= item["target_ms"]
            report = {
                "os": platform.platform(),
                "processor": platform.processor(),
                "python": platform.python_version(),
                "mode": "uvicorn single worker; loopback HTTP; warm connections; no reload",
                "data_dir": str(root),
                "session_id": info["id"],
                "code_bytes": len(content.encode()),
                "results": results,
                "ui_cold_warm": "not measured",
                "thirty_minute_soak": "not performed",
            }
            Path(args.output).write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps({key: value["p95_ms"] for key, value in results.items()}))
    finally:
        process.terminate()
        process.wait(timeout=10)
        logfile.close()


if __name__ == "__main__":
    main()
