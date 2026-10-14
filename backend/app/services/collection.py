"""Task preparation, stable research identities, drafts and versioned resource references."""

import json
import mimetypes
import secrets
from dataclasses import replace
from datetime import timedelta
from io import BytesIO

import jwt
from pypdf import PdfReader

from app.domain.errors import DomainError
from app.domain.events import SCHEMA_VERSION, parse_time
from app.repositories.database import encode
from app.services.attachments import parse_file
from app.services.files import atomic_write, digest, resolve_ref
from app.settings import ROOT


class CollectionService:
    def __init__(self, core):
        self.c = core

    def publish(self, task):
        c = self.c
        for item in task.get("resources", []):
            source = resolve_ref(ROOT / "config/resources", item["file"])
            if not 0 < source.stat().st_size <= c.settings.resource_max:
                raise ValueError("教材资源为空或超过 RESOURCE_MAX_BYTES 上限")
            raw = source.read_bytes()
            ref = f"resources/{item['id']}/{item['version']}/{source.name}"
            mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            text, status = "", "unsupported"
            if source.suffix.lower() in {".txt", ".md", ".html", ".pdf", ".docx"}:
                try:
                    text = parse_file(
                        source.name,
                        mime,
                        raw,
                        replace(c.settings, attachment_max=c.settings.resource_max),
                    )
                    status = "ready"
                except ValueError:
                    status = "unsupported"
                except Exception:
                    status = "failed"
            body = {
                **item,
                "storage_ref": ref,
                "mime": mime,
                "sha256": digest(raw),
                "extracted_text": text,
                "ai_input_status": status,
                "extracted_text_ref": ref + ".txt" if text else None,
            }
            if item.get("reference_mode") == "current_page":
                texts = [text] if text else [""]
                if source.suffix.lower() == ".pdf":
                    reader = PdfReader(BytesIO(raw))
                    if reader.is_encrypted or len(reader.pages) > 100:
                        raise ValueError("不支持加密或超过 100 页的教材 PDF")
                    texts = [page.extract_text() or "" for page in reader.pages]
                elif item.get("page_separator"):
                    texts = text.split(item["page_separator"])
                mapping = item.get("printed_pages", [])
                if mapping and len(mapping) != len(texts):
                    raise ValueError("印刷页码映射与文件页数不一致")
                if item.get("reviewed_text_file"):
                    if source.suffix.lower() != ".pdf":
                        raise ValueError("校对逐页文字仅适用于 PDF 教材")
                    sidecar = resolve_ref(ROOT / "config/resources", item["reviewed_text_file"])
                    if not 0 < sidecar.stat().st_size <= c.settings.resource_max:
                        raise ValueError("校对文字文件为空或超过资源大小上限")
                    reviewed_raw = sidecar.read_bytes()
                    reviewed = json.loads(reviewed_raw.decode("utf-8-sig"))
                    rows = reviewed.get("pages", [])
                    if (
                        reviewed.get("schema_version") != "reviewed-page-text-v1"
                        or not reviewed.get("version")
                        or reviewed.get("source_pdf_sha256") != digest(raw)
                        or len(rows) != len(texts)
                    ):
                        raise ValueError("校对文字版本、PDF 来源或页数不匹配")
                    source_pages = item.get("source_pdf_pages", [])
                    if source_pages and len(source_pages) != len(texts):
                        raise ValueError("原整册页码映射与文件页数不一致")
                    for i, row in enumerate(rows):
                        if (
                            type(row.get("page")) is not int
                            or row["page"] != i + 1
                            or row.get("printed_page") != (mapping[i] if mapping else None)
                            or (source_pages and row.get("source_pdf_page") != source_pages[i])
                            or not isinstance(row.get("text"), str)
                            or not row["text"].strip()
                        ):
                            raise ValueError("校对文字页序、映射或正文无效")
                    if sum(len(row["text"]) for row in rows) > 200000:
                        raise ValueError("校对文字超过 200000 字符")
                    body.update(
                        raw_ocr_ref=ref + ".ocr.pages.json",
                        reviewed_text_ref=ref + ".reviewed.json",
                        reviewed_text_sha256=digest(reviewed_raw),
                        reviewed_text_version=reviewed["version"],
                        text_source="reviewed_page_text",
                    )
                    raw_pages = [{"page": i + 1, "text": t} for i, t in enumerate(texts)]
                    texts = [row["text"] for row in rows]
                    text = "\n\n".join(texts)
                    body.update(extracted_text=text, extracted_text_ref=ref + ".txt")
                pages = [
                    {
                        "page": i + 1,
                        "printed_page": mapping[i] if mapping else None,
                        "text": content,
                        "ai_input_status": "ready" if content.strip() else "unsupported",
                    }
                    for i, content in enumerate(texts)
                ]
                body.update(
                    pages=pages,
                    page_count=len(pages),
                    page_content_ref=ref + ".pages.json",
                    ai_input_status="ready" if any(t.strip() for t in texts) else "unsupported",
                )
            elif item.get("reviewed_text_file"):
                raise ValueError("校对文字要求 reference_mode=current_page")
            with c.db.transaction() as conn:
                old = conn.execute(
                    "SELECT body FROM resources WHERE id=? AND version=?",
                    (item["id"], item["version"]),
                ).fetchone()
                if old and json.loads(old[0]) != body:
                    raise ValueError("资源版本内容变更，请发布新的 version")
                atomic_write(c.settings.data_dir / ref, raw)
                if text:
                    atomic_write(c.settings.data_dir / (ref + ".txt"), text)
                if body.get("page_content_ref"):
                    atomic_write(c.settings.data_dir / body["page_content_ref"], encode(pages))
                if body.get("reviewed_text_ref"):
                    atomic_write(c.settings.data_dir / body["reviewed_text_ref"], reviewed_raw)
                    atomic_write(c.settings.data_dir / body["raw_ocr_ref"], encode(raw_pages))
                conn.execute(
                    "INSERT OR IGNORE INTO resources VALUES(?,?,?)",
                    (item["id"], item["version"], encode(body)),
                )

    def entry(self, seat, token):
        c = self.c
        with c.db.read() as conn:
            source = conn.execute("SELECT * FROM seats WHERE seat_no=?", (seat,)).fetchone()
            person = conn.execute(
                "SELECT participant_id FROM seat_participants WHERE seat_no=?", (seat,)
            ).fetchone()
            if (
                not source
                or not person
                or not secrets.compare_digest(source["token_hash"], digest(token))
                or parse_time(source["expires_at"]) < c.clock()
            ):
                raise DomainError("INVALID_SEAT", "入口无效或已过期。", 401)
        claims = {
            "sub": person[0],
            "seat": seat,
            "scope": "entry",
            "iat": c.clock(),
            "exp": c.clock() + timedelta(hours=8),
        }
        c.research_access.require(person[0])
        return {
            "participant_id": person[0],
            "seat_no": seat,
            "server_now": c.now(),
            "token": jwt.encode(claims, c.settings.secret, algorithm="HS256"),
            "tasks": self.tasks(claims),
        }

    def identity(self, bearer):
        try:
            claims = jwt.decode(
                bearer.removeprefix("Bearer "),
                self.c.settings.secret,
                algorithms=["HS256"],
                options={"require": ["exp", "sub", "scope", "seat"]},
            )
            if claims["scope"] not in {"entry", "session"}:
                raise ValueError()
            self.c.research_access.require(claims["sub"])
            with self.c.db.read() as conn:
                binding = conn.execute(
                    "SELECT participant_id FROM seat_participants WHERE seat_no=?",
                    (claims["seat"],),
                ).fetchone()
                if not binding or binding[0] != claims["sub"]:
                    raise ValueError()
            return claims
        except (ValueError, KeyError, jwt.PyJWTError):
            raise DomainError("UNAUTHORIZED", "请使用当前分配的入口重新进入。", 401) from None

    def tasks(self, identity):
        with self.c.db.read() as conn:
            rows = conn.execute(
                "SELECT a.*,t.body FROM task_assignments a JOIN task_configs t ON t.id=a.task_id WHERE a.participant_id=?",
                (identity["sub"],),
            ).fetchall()
            active = conn.execute(
                "SELECT id,task_id,status FROM sessions WHERE participant_id=? AND status IN ('PREPARING','ACTIVE','ENDING')",
                (identity["sub"],),
            ).fetchone()
        return [
            {
                "task_id": r["task_id"],
                "assignment_id": r["id"],
                "title": json.loads(r["body"])["title"],
                "summary": json.loads(r["body"]).get("summary", "英语课堂互动网站制作"),
                "active_session_id": active["id"]
                if active and active["task_id"] == r["task_id"]
                else None,
            }
            for r in rows
        ]

    def prepare(self, identity, task_id, assignment_id, writer_id):
        from app.services.core import uid

        c = self.c
        c.research_access.require(identity["sub"])
        c.expire()
        with c.db.transaction() as conn:
            assignment = conn.execute(
                "SELECT * FROM task_assignments WHERE participant_id=? AND task_id=?",
                (identity["sub"], task_id),
            ).fetchone()
            if not assignment or (assignment_id and assignment_id != assignment["id"]):
                raise DomainError("FORBIDDEN", "任务未分配给当前参与者。", 403)
            existing = conn.execute(
                "SELECT * FROM sessions WHERE participant_id=? AND status IN ('PREPARING','ACTIVE','ENDING')",
                (identity["sub"],),
            ).fetchone()
            if existing:
                s = dict(existing)
                if s["task_id"] != task_id:
                    raise DomainError("TASK_ACTIVE", "请先结束当前任务，再进入其他任务。", 409)
                c.claim_writer(conn, s, writer_id)
                if s["status"] == "ENDING":
                    conn.execute(
                        "UPDATE sessions SET status='ACTIVE',detach_at=NULL WHERE id=?", (s["id"],)
                    )
            else:
                task = json.loads(
                    conn.execute("SELECT body FROM task_configs WHERE id=?", (task_id,)).fetchone()[
                        0
                    ]
                )
                task["condition_id"] = assignment["condition_id"]
                task["model_config"] = {
                    "provider": c.settings.ai_provider,
                    "model": "fake-local-v1"
                    if c.settings.ai_provider == "fake"
                    else c.settings.deepseek_model,
                }
                sid, now = uid(), c.now()
                conn.execute(
                    "INSERT INTO sessions(id,participant_id,seat_no,task_id,task_version,task_json,status,last_seen_at,created_at,schema_version,writer_id,lease_until) VALUES(?,?,?,?,?,?,'PREPARING',?,?,?,?,?)",
                    (
                        sid,
                        identity["sub"],
                        identity["seat"],
                        task_id,
                        task["version"],
                        encode(task),
                        now,
                        now,
                        SCHEMA_VERSION,
                        writer_id,
                        (c.clock() + timedelta(seconds=60)).isoformat(),
                    ),
                )
                s = c.db.session(conn, sid)
            s = c.db.session(conn, s["id"])
        return c.public_session(s) | {"token": c.token(s)}

    def prerequisite(self, sid, body):
        c = self.c
        with c.db.transaction() as conn:
            s = c.db.session(conn, sid)
            task = json.loads(s["task_json"])
            questions = task.get("prerequisite", {}).get("questions", [])
            values = {r.question_id: r.answer_value for r in body.responses}
            if (
                body.version != task["prerequisite"]["version"]
                or len(values) != len(body.responses)
                or set(values) != {q["id"] for q in questions}
            ):
                raise DomainError("QUESTIONNAIRE_INVALID", "请完成全部背景问题。")
            for q in questions:
                value = values[q["id"]]
                if value is None and q.get("allow_refusal"):
                    continue
                if isinstance(value, bool) or value not in [o["value"] for o in q["options"]]:
                    raise DomainError("QUESTIONNAIRE_INVALID", "答案不在允许范围内。")
            responses = [
                {"question_id": q["id"], "answer_value": values[q["id"]]} for q in questions
            ]
            frozen = {"version": body.version, "responses": responses}
            if s["prerequisite_json"]:
                if json.loads(s["prerequisite_json"]) != frozen:
                    raise DomainError("QUESTIONNAIRE_FROZEN", "已提交的背景回答不能覆盖。", 409)
                return c.public_session(s)
            if s["status"] != "PREPARING":
                raise DomainError("SESSION_ENDED", "当前会话不能提交背景回答。", 409)
            c.emit(
                conn,
                sid,
                "task_prerequisite_completed",
                {"completed_at": body.occurred_at, "responses": responses},
                **c.occurrence(body.model_dump()),
            )
            conn.execute(
                "UPDATE sessions SET prerequisite_json=? WHERE id=?", (encode(frozen), sid)
            )
            return c.public_session(c.db.session(conn, sid))

    def start(self, sid, body):
        c = self.c
        with c.db.transaction() as conn:
            s = c.db.session(conn, sid)
            if s["started_at"]:
                return c.public_session(s)
            if s["status"] != "PREPARING" or not s["prerequisite_json"]:
                raise DomainError("PREREQUISITE_REQUIRED", "请先完成背景问卷。", 409)
            when = parse_time(body.occurred_at)
            if when < parse_time(s["created_at"]) - timedelta(
                seconds=5
            ) or when > c.clock() + timedelta(seconds=30):
                raise DomainError("INVALID_TIME", "开始时间超出会话范围。")
            conn.execute(
                "UPDATE sessions SET status='ACTIVE',started_at=?,last_seen_at=? WHERE id=?",
                (body.occurred_at, c.now(), sid),
            )
            c.emit(
                conn, sid, "task_started", {"entry_page": "task"}, **c.occurrence(body.model_dump())
            )
            return c.public_session(c.db.session(conn, sid))

    def task(self, session):
        task = json.loads(session["task_json"])
        if session["status"] == "PREPARING" and not session["prerequisite_json"]:
            return {k: task[k] for k in ("task_id", "version", "title", "prerequisite")}
        return task | {
            "upload": {
                "max_bytes": self.c.settings.attachment_max,
                "types": self.c.settings.attachment_types,
            },
            "ai_provider": task.get("model_config", {}).get(
                "provider", self.c.settings.ai_provider
            ),
        }

    def resources(self, s):
        if not s["prerequisite_json"] and s["schema_version"] == SCHEMA_VERSION:
            raise DomainError("PREREQUISITE_REQUIRED", "请先完成背景问卷。", 409)
        with self.c.db.read() as conn:
            return [
                json.loads(
                    conn.execute(
                        "SELECT body FROM resources WHERE id=? AND version=?",
                        (r["id"], r["version"]),
                    ).fetchone()[0]
                )
                for r in json.loads(s["task_json"]).get("resources", [])
            ]

    def resource(self, s, rid, version):
        resource = next(
            (r for r in self.resources(s) if r["id"] == rid and r["version"] == version), None
        )
        if not resource:
            raise DomainError("NOT_FOUND", "当前任务没有此资源版本。", 404)
        return resource

    def save_draft(self, sid, did, body):
        c = self.c
        with c.db.transaction() as conn:
            c.active(conn, sid)
            old = c.db.get(conn, "request_drafts", did)
            if old and old["session_id"] != sid:
                raise DomainError("NOT_FOUND", "草稿不存在。", 404)
            data = body.model_dump()
            for aid in data["attachment_ids"]:
                c.owned(conn, "attachments", aid, sid)
            for rid in data["reference_ids"]:
                reference = c.owned(conn, "resource_references", rid, sid)
                if reference["draft_id"] != did:
                    raise DomainError("REFERENCE_MISMATCH", "引用不属于此草稿。")
            rev_id = f"{did}-{body.revision}"
            rev = c.db.get(conn, "draft_revisions", rev_id)
            if rev and rev["content"] != body.content:
                raise DomainError("REVISION_CONFLICT", "草稿版本内容冲突。", 409)
            if not rev:
                c.db.put(
                    conn,
                    "draft_revisions",
                    rev_id,
                    sid,
                    {"draft_id": did, "revision": body.revision, "content": body.content},
                )
            if not old or body.revision >= old["revision"]:
                c.db.put(conn, "request_drafts", did, sid, data | {"updated_at": c.now()})
        return {"id": did, **data}

    def reference(self, sid, did, body, remove_id=None):
        c = self.c
        with c.db.transaction() as conn:
            s = c.active(conn, sid)
            if remove_id:
                item = c.owned(conn, "resource_references", remove_id, sid)
                if item["draft_id"] != did:
                    raise DomainError("NOT_FOUND", "引用不属于此草稿。", 404)
                if item["status"] == "REMOVED":
                    return item
                item.update(status="REMOVED", draft_revision=body.draft_revision)
                name = "resource_reference_removed"
            else:
                rid = body.reference_id
                old = c.db.get(conn, "resource_references", rid)
                if old:
                    if (
                        old["session_id"] != sid
                        or old["draft_id"] != did
                        or old["resource_id"] != body.resource_id
                        or old["resource_version"] != body.resource_version
                        or old.get("page") != body.page
                        or old.get("fragment") != body.fragment
                        or old.get("reference_purpose") != body.reference_purpose
                        or old.get("reference_note") != body.reference_note
                    ):
                        raise DomainError("ID_CONFLICT", "引用编号冲突。", 409)
                    return old
                resource = self.resource(s, body.resource_id, body.resource_version)
                if resource.get("reference_mode") == "current_page":
                    page = next((p for p in resource["pages"] if p["page"] == body.page), None)
                    if not page or body.fragment is not None:
                        raise DomainError("PAGE_REQUIRED", "请选择可定位的教材当前整页。")
                    if page["ai_input_status"] != "ready":
                        raise DomainError(
                            "PAGE_UNSUPPORTED", "此页没有可读取文字，不能作为文字引用。"
                        )
                else:
                    # Legacy resources retain resource-level reference semantics.
                    page = None
                if resource["ai_input_status"] != "ready":
                    raise DomainError(
                        "RESOURCE_UNSUPPORTED", "当前模型不能读取此资源；仍可浏览或用于作品。", 409
                    )
                item = {
                    "reference_id": rid,
                    "resource_id": body.resource_id,
                    "resource_version": body.resource_version,
                    "draft_id": did,
                    "draft_revision": body.draft_revision,
                    "page": body.page,
                    "fragment": body.fragment,
                    "reference_purpose": body.reference_purpose,
                    "reference_note": body.reference_note,
                    "reference_mode": resource.get("reference_mode", "resource"),
                    "extracted_text": page["text"] if page else resource["extracted_text"],
                    "printed_page": page["printed_page"] if page else None,
                    "created_at": body.occurred_at,
                    "status": "ACTIVE",
                }
                name = "resource_reference_added"
            from app.domain.events import FIELDS

            payload = {k: item[k] for k in FIELDS[name]}
            c.db.put(conn, "resource_references", item["reference_id"], sid, item)
            c.emit(conn, sid, name, payload, **c.occurrence(body.model_dump()))
            return item
