import json
import secrets
from datetime import timedelta

import jwt

from app.domain.errors import DomainError
from app.services.files import atomic_write

BRIDGE = r"""<script>
(()=>{'use strict';const run=__RUN__,channel=__CHANNEL__;let phase='load';
 const stringify=v=>{try{return typeof v==='string'?v:JSON.stringify(v)}catch{return String(v)}};
 const post=(kind,extra={})=>parent.postMessage({app:'teaching-preview',run_id:run,channel,kind,...extra},'*');
 for(const kind of ['log','warn','error']){const original=console[kind].bind(console);console[kind]=(...args)=>{original(...args);post(kind,{text:args.map(stringify).join(' ').slice(0,20000),error_type:'console.'+kind,error_phase:phase})}}
 addEventListener('error',e=>post('error',{text:String(e.message||'Resource load error').slice(0,20000),error_type:e.error?.name||'Error',error_phase:phase,line:e.lineno||null,column:e.colno||null,stack:e.error?.stack||null}));
 addEventListener('unhandledrejection',e=>post('error',{text:String(e.reason?.message||e.reason).slice(0,20000),error_type:'UnhandledRejection',error_phase:phase,stack:e.reason?.stack||null}));
 for(const type of ['click','change','submit']){addEventListener(type,e=>{const target=e.target?.closest?.('button,input,select,[role=button],form,a');if(!target)return;phase='interaction';post('interaction',{interaction_type:type,target:(target.id||target.getAttribute('aria-label')||target.textContent||target.tagName).trim().slice(0,500),outcome:null})},true)}
 addEventListener('load',()=>{post('ready');phase='interaction'},{once:true});
})();
</script>"""


class PreviewService:
    def __init__(self, core):
        self.core = core

    def run(self, sid, command):
        c, d = self.core, command.model_dump()
        with c.db.read() as conn:
            old = c.db.get(conn, "preview_runs", d["run_id"], sid)
        if old:
            if old["command"] != d:
                raise DomainError("ID_CONFLICT", "运行编号已被不同内容使用。", 409)
            if old["status"] == "FAILED":
                raise DomainError("SAVE_FAILED", "本次保存失败，请重新点击运行。", 503, True)
            return self.result(old)
        try:
            with c.db.transaction() as conn:
                c.active(conn, sid)
                revision = c.save_revision(
                    conn, sid, "code", d["content"], d["revision"], allow_historical=True
                )
                channel = secrets.token_urlsafe(24)
                bridge = BRIDGE.replace("__RUN__", json.dumps(d["run_id"])).replace(
                    "__CHANNEL__", json.dumps(channel)
                )
                # Bridge runs before user scripts; immutable original source is not modified.
                ref = f"previews/{sid}/{d['run_id']}.html"
                html = d["content"]
                if html.lstrip().lower().startswith("<!doctype") and ">" in html:
                    index = html.index(">") + 1
                    html = html[:index] + bridge + html[index:]
                else:
                    html = bridge + html
                atomic_write(c.settings.data_dir / ref, html)
                body = {
                    "command": d,
                    "channel": channel,
                    "content_ref": ref,
                    "revision_id": revision["id"],
                    "code_revision": d["revision"],
                    "status": "SAVED",
                    "created_at": c.now(),
                }
                c.db.put(conn, "preview_runs", d["run_id"], sid, body)
                c.emit(
                    conn,
                    sid,
                    "preview_run",
                    {
                        "run_id": d["run_id"],
                        "code_revision": d["revision"],
                        "code_snapshot_ref": revision["content_ref"],
                        "save_status": "saved",
                    },
                    occurred_at=d["occurred_at"],
                )
            return self.result({"id": d["run_id"], "session_id": sid, **body})
        except OSError as exc:
            with c.db.transaction() as conn:
                c.db.put(
                    conn,
                    "preview_runs",
                    d["run_id"],
                    sid,
                    {
                        "command": d,
                        "status": "FAILED",
                        "created_at": c.now(),
                        "error_type": type(exc).__name__,
                    },
                )
                c.emit(
                    conn,
                    sid,
                    "preview_run",
                    {
                        "run_id": d["run_id"],
                        "code_revision": d["revision"],
                        "code_snapshot_ref": None,
                        "save_status": "failed",
                    },
                    occurred_at=d["occurred_at"],
                )
            raise DomainError("SAVE_FAILED", "无法保存预览，原预览保持不变。", 503, True) from exc

    def result(self, run):
        token = jwt.encode(
            {
                "scope": "preview",
                "rid": run["id"],
                "sid": run["session_id"],
                "exp": self.core.clock() + timedelta(minutes=10),
            },
            self.core.settings.secret,
            algorithm="HS256",
        )
        return {
            "run_id": run["id"],
            "channel": run["channel"],
            "code_revision": run["code_revision"],
            "url": f"/api/v1/preview-content/{run['id']}?signature={token}",
        }

    def content(self, run_id, signature):
        try:
            claims = jwt.decode(signature, self.core.settings.secret, algorithms=["HS256"])
            if claims["scope"] != "preview" or claims["rid"] != run_id:
                raise ValueError()
        except (jwt.PyJWTError, KeyError, ValueError):
            raise DomainError("INVALID_SIGNATURE", "预览地址已过期，请再次运行。", 401) from None
        with self.core.db.read() as conn:
            run = self.core.owned(conn, "preview_runs", run_id, claims["sid"])
        return self.core.settings.data_dir / run["content_ref"]

    def message(self, sid, run_id, message):
        c, d = self.core, message.model_dump()
        with c.db.transaction() as conn:
            c.active(conn, sid)
            run = c.owned(conn, "preview_runs", run_id, sid)
            if d["channel"] != run.get("channel"):
                raise DomainError("INVALID_CHANNEL", "预览通道不匹配。", 403)
            old = c.db.get(conn, "preview_logs", d["message_id"], sid)
            if old:
                if old["message"] != d or old["run_id"] != run_id:
                    raise DomainError("ID_CONFLICT", "日志编号冲突。", 409)
                return old
            body = {"run_id": run_id, "message": d, "created_at": c.now()}
            c.db.put(conn, "preview_logs", d["message_id"], sid, body)
            if d["kind"] == "ready" and run["status"] != "READY":
                run.update(status="READY", ready_at=c.now())
                c.db.put(conn, "preview_runs", run_id, sid, run)
                c.emit(conn, sid, "preview_ready", {"run_id": run_id})
            elif d["kind"] == "error":
                c.emit(
                    conn,
                    sid,
                    "preview_error_detected",
                    {
                        "run_id": run_id,
                        "error_id": d["message_id"],
                        "error_phase": d["error_phase"],
                        "error_type": d["error_type"],
                        "error_message": d["text"],
                        "line": d["line"],
                        "column": d["column"],
                        "stack": d["stack"],
                    },
                )
            elif d["kind"] == "interaction":
                c.emit(
                    conn,
                    sid,
                    "preview_interacted",
                    {
                        "run_id": run_id,
                        "interaction_type": d["interaction_type"],
                        "target": d["target"],
                        "outcome": d["outcome"],
                    },
                )
        return {"id": d["message_id"], **body}
