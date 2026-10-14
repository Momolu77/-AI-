"""Show and record a synchronization marker on a researcher-launched localhost page."""

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer

from common import bootstrap, load_core

bootstrap()
from app.services.capture import CaptureService  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--participant-id", required=True)
parser.add_argument("--recording-id", required=True)
parser.add_argument("--env-file", default=".env.local")
parser.add_argument("--port", type=int, default=0)
args = parser.parse_args()
core = load_core(args.env_file)
service = CaptureService(core)
capability = secrets.token_urlsafe(32)
page = """<!doctype html><meta charset="utf-8"><title>录屏同步标记</title>
<style>body{font:24px system-ui;text-align:center;padding:60px}#marker{padding:60px;background:#fff;color:#000;border:20px solid #000;overflow-wrap:anywhere}button{padding:20px;margin:25px}</style>
<h1>录屏同步标记</h1><p>请在录屏开始、结束或分段后呈现标记。视频位置须课后按实际 PTS 核验。</p><button id="show">呈现新标记</button><div id="marker">等待呈现</div><p id="status"></p>
<script>
const pid=__PID__,rid=__RID__,producer='marker-'+crypto.randomUUID();let seq=0,pending=null,calibration=null,offset=0;
const clock=async()=>{const start=Date.now(),m=performance.now(),server=await(await fetch(location.pathname+'?clock')).json(),end=Date.now();offset=Date.parse(server.server_time)-(start+end)/2;const body={id:crypto.randomUUID(),producer_id:producer,client_send_time:new Date(start).toISOString(),client_receive_time:new Date(end).toISOString(),server_time:server.server_time,round_trip_ms:performance.now()-m,offset_ms:offset,uncertainty_ms:(performance.now()-m)/2};const r=await fetch(location.pathname+'/calibration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error('校准记录失败');calibration=body.id};
const send=async()=>{try{const r=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pending)});if(!r.ok)throw new Error(await r.text());document.getElementById('status').textContent='标记已记录。';pending=null;show.disabled=false}catch(e){document.getElementById('status').textContent='尚未同步，点击重试：'+e.message;show.disabled=false;show.textContent='重试同步'}};
show.onclick=async()=>{show.disabled=true;if(pending){send();return}try{await clock()}catch(e){document.getElementById('status').textContent=e.message;show.disabled=false;return}const marker_id=crypto.randomUUID();marker.textContent=marker_id;requestAnimationFrame(()=>requestAnimationFrame(()=>{const raw=new Date().toISOString(),id=crypto.randomUUID();pending={event_id:id,participant_id:pid,occurred_at:new Date(Date.parse(raw)+offset).toISOString(),transport:{producer_id:producer,producer_seq:++seq,raw_time:raw,monotonic_ms:performance.now(),clock_calibration_id:calibration,time_source:'client_clock',action_id:id,causal_parent_ids:[]},payload:{marker_id,recording_id:rid,displayed_at:new Date(Date.parse(raw)+offset).toISOString(),clock_calibration_id:calibration}};send()}))};
</script>""".replace("__PID__", json.dumps(args.participant_id)).replace(
    "__RID__", json.dumps(args.recording_id)
)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/" + capability + "?clock":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"server_time": core.now()}).encode())
            return
        if self.path != "/" + capability:
            self.send_error(404)
            return
        raw = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path not in {"/" + capability, "/" + capability + "/calibration"}:
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 20000:
                raise ValueError("请求长度无效")
            row = json.loads(self.rfile.read(size))
            if self.path.endswith("/calibration"):
                body = service.calibration(row)
            elif (
                row["participant_id"] != args.participant_id
                or row["payload"]["recording_id"] != args.recording_id
            ):
                raise ValueError("录屏或参与者不匹配")
            else:
                body = service.marker(row)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())
        except (ValueError, KeyError) as exc:
            self.send_error(400, str(exc).encode("ascii", errors="replace").decode())


server = HTTPServer(("127.0.0.1", args.port), Handler)
print(f"在录屏所在浏览器打开 http://127.0.0.1:{server.server_port}/{capability}", flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    server.server_close()
