import json
import os
import shutil

from app.domain.errors import DomainError
from app.repositories.database import encode
from app.services.files import atomic_write, digest


class SubmissionService:
    def __init__(self, core):
        self.core = core

    def submit(self, sid, command):
        c, data = self.core, command.model_dump()
        subid = data["submission_id"]
        with c.db.transaction() as conn:
            old = c.db.get(conn, "submissions", subid)
            if old:
                if old["session_id"] != sid or old["command"] != data:
                    raise DomainError("ID_CONFLICT", "提交编号已被不同内容使用。", 409)
                return old
            c.active(conn, sid)
            if any(row["status"] == "PENDING" for row in c.db.all(conn, "submissions", sid)):
                raise DomainError("SUBMISSION_PENDING", "请先核对上一份提交结果。", 409, True)
            if c.db.get(conn, "snapshots", data["snapshot_id"]):
                raise DomainError("ID_CONFLICT", "快照编号已存在。", 409)
            if conn.execute(
                "SELECT 1 FROM submissions WHERE json_extract(body,'$.snapshot_id')=?",
                (data["snapshot_id"],),
            ).fetchone():
                raise DomainError("ID_CONFLICT", "快照编号已被其他提交预留。", 409)
            if any(len(data[k].encode("utf-8")) > c.settings.code_max for k in ("code", "plan")):
                raise DomainError("CONTENT_TOO_LARGE", "作品超过保存大小上限。", 413)
            body = {
                "command": data,
                "status": "PENDING",
                "snapshot_id": data["snapshot_id"],
                "submission_no": len(c.db.all(conn, "submissions", sid)) + 1,
                "created_at": c.now(),
                "design_rationale": data["design_rationale"],
            }
            c.db.put(conn, "submissions", subid, sid, body)
            c.emit(
                conn,
                sid,
                "submit_confirmed",
                {
                    k: data[k]
                    for k in ("submission_id", "code_revision", "plan_revision", "snapshot_id")
                },
                **c.occurrence(data),
            )
        return self.finish({"id": subid, "session_id": sid, **body})

    def finish(self, submission):
        c, sid, subid = self.core, submission["session_id"], submission["id"]
        d = submission["command"]
        relative = f"submissions/{sid}/{subid}"
        final = c.settings.data_dir / relative
        staging = final.with_name(f".pending-{subid}")
        try:
            if not final.exists():
                staging.mkdir(parents=True, exist_ok=True)
                manifest = {
                    "session_id": sid,
                    "submission_id": subid,
                    "snapshot_id": d["snapshot_id"],
                    "code_revision": d["code_revision"],
                    "plan_revision": d["plan_revision"],
                    "confirmed_at": d["occurred_at"],
                    "files": {"index.html": digest(d["code"]), "plan.txt": digest(d["plan"])},
                }
                atomic_write(staging / "index.html", d["code"])
                atomic_write(staging / "plan.txt", d["plan"])
                if d.get("design_rationale") is not None:
                    manifest["files"]["design_rationale.txt"] = digest(d["design_rationale"])
                    atomic_write(staging / "design_rationale.txt", d["design_rationale"])
                manifest["design_rationale_status"] = (
                    "provided" if d.get("design_rationale", "") else "missing"
                )
                atomic_write(staging / "manifest.json", encode(manifest))
                checksums = {**manifest["files"], "manifest.json": digest(encode(manifest))}
                atomic_write(
                    staging / "checksums.sha256",
                    "\n".join(f"{sha}  {name}" for name, sha in checksums.items()) + "\n",
                )
                self.verify(staging, d)
                os.replace(staging, final)
            self.verify(final, d)
            with c.db.transaction() as conn:
                old = c.owned(conn, "submissions", subid, sid)
                if old["status"] == "SUCCEEDED":
                    return old
                code = c.save_revision(
                    conn, sid, "code", d["code"], d["code_revision"], allow_historical=True
                )
                plan = c.save_revision(
                    conn, sid, "plan", d["plan"], d["plan_revision"], allow_historical=True
                )
                snapshot = {
                    "code_ref": f"{relative}/index.html",
                    "plan_ref": f"{relative}/plan.txt",
                    "manifest_ref": f"{relative}/manifest.json",
                    "checksums_ref": f"{relative}/checksums.sha256",
                    "sha256": digest(d["code"]),
                    "created_at": c.now(),
                    "design_rationale_ref": f"{relative}/design_rationale.txt"
                    if d.get("design_rationale") is not None
                    else None,
                }
                c.db.put(conn, "snapshots", d["snapshot_id"], sid, snapshot)
                submission.update(
                    status="SUCCEEDED",
                    code_revision_id=code["id"],
                    plan_revision_id=plan["id"],
                    completed_at=c.now(),
                )
                c.db.put(conn, "submissions", subid, sid, submission)
                c.emit(
                    conn,
                    sid,
                    "submit_succeeded",
                    {"submission_id": subid, "snapshot_id": d["snapshot_id"]},
                )
            return submission
        except (OSError, ValueError, DomainError) as exc:
            if staging.exists():
                shutil.rmtree(staging)
            with c.db.transaction() as conn:
                submission.update(
                    status="FAILED",
                    error_message="快照保存失败，请保留草稿后重新确认提交。",
                    error_type=type(exc).__name__,
                )
                c.db.put(conn, "submissions", subid, sid, submission)
                c.emit(
                    conn,
                    sid,
                    "submit_failed",
                    {
                        "submission_id": subid,
                        "error_type": type(exc).__name__,
                        "error_message": submission["error_message"],
                        "retryable": True,
                    },
                )
            return submission

    @staticmethod
    def verify(folder, command):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for filename, sha in manifest["files"].items():
            if (
                filename not in {"index.html", "plan.txt", "design_rationale.txt"}
                or digest((folder / filename).read_bytes()) != sha
            ):
                raise ValueError("快照校验失败")
        if (folder / "index.html").read_text(encoding="utf-8") != command["code"] or (
            folder / "plan.txt"
        ).read_text(encoding="utf-8") != command["plan"]:
            raise ValueError("快照与确认内容不一致")
        if (
            command.get("design_rationale") is not None
            and (folder / "design_rationale.txt").read_text(encoding="utf-8")
            != command["design_rationale"]
        ):
            raise ValueError("设计说明与确认内容不一致")

    def recover(self):
        with self.core.db.read() as conn:
            rows = conn.execute("SELECT id,session_id,body FROM submissions").fetchall()
        for row in rows:
            body = json.loads(row["body"])
            if body["status"] == "PENDING":
                self.finish({"id": row["id"], "session_id": row["session_id"], **body})
