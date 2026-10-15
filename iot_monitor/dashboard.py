"""Tiny web dashboard + JSON API using only the standard library."""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .schema import METRICS

_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IoT Sensor Monitor</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--text:#1b1f24;--muted:#5b6570;--line:#d9dee5;--accent:#2563eb;--warn:#b45309;--crit:#b91c1c}
@media (prefers-color-scheme:dark){:root{--bg:#12151a;--card:#1b2027;--text:#e8ebef;--muted:#9aa5b1;--line:#2c343e;--accent:#6ea0ff;--warn:#f0b35a;--crit:#ff7b7b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);margin-bottom:16px}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:120px}
.stat b{display:block;font-size:20px}.stat span{color:var(--muted);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.card h3{margin:0;font-size:13px;color:var(--muted);font-weight:600}.val{font-size:22px;font-weight:600}
canvas{width:100%;height:70px;display:block}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);font-size:13px}th{color:var(--muted);font-weight:600}
.sev{font-weight:600}.sev.warning{color:var(--warn)}.sev.critical{color:var(--crit)}
.wrap{overflow-x:auto}
</style></head><body><main>
<h1>IoT Sensor Monitor</h1><div class="sub">Live readings, stored in SQLite, with streaming anomaly alerts. Refreshes every 2 s.</div>
<div class="stats" id="stats"></div><div class="grid" id="grid"></div>
<h2 style="font-size:16px">Recent alerts</h2>
<div class="wrap"><table><thead><tr><th>Time</th><th>Severity</th><th>Type</th><th>Series</th><th>Message</th></tr></thead><tbody id="alerts"></tbody></table></div>
</main><script>
const $=id=>document.getElementById(id);
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function j(u){const r=await fetch(u);return r.json()}
function draw(cv,pts){
  const dpr=window.devicePixelRatio||1,w=cv.clientWidth,h=cv.clientHeight;cv.width=w*dpr;cv.height=h*dpr;
  const g=cv.getContext('2d');g.scale(dpr,dpr);g.clearRect(0,0,w,h);if(pts.length<2)return;
  const v=pts.map(p=>p.value),lo=Math.min(...v),hi=Math.max(...v),pad=(hi-lo||1)*0.15;
  const x=i=>i/(pts.length-1)*(w-4)+2,y=val=>h-4-(val-(lo-pad))/((hi+pad)-(lo-pad))*(h-8);
  g.strokeStyle=css('--accent');g.lineWidth=1.6;g.beginPath();
  pts.forEach((p,i)=>i?g.lineTo(x(i),y(p.value)):g.moveTo(x(i),y(p.value)));g.stroke();
}
async function refresh(){
  const [st,latest,al]=await Promise.all([j('/api/stats'),j('/api/latest'),j('/api/alerts?limit=15')]);
  $('stats').innerHTML=[['Readings',st.readings],['Series',st.series],['Alerts',st.alerts]]
    .map(([k,v])=>`<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');
  const grid=$('grid');
  for(const s of latest){
    const id=`c-${s.device}-${s.metric}`;let card=document.getElementById(id);
    if(!card){card=document.createElement('div');card.className='card';card.id=id;
      card.innerHTML=`<h3>${esc(s.device)} · ${esc(s.metric)}</h3><div class="val"></div><canvas></canvas>`;grid.appendChild(card);}
    card.querySelector('.val').textContent=`${s.value.toFixed(1)} ${s.unit}`;
    const pts=await j(`/api/series?device=${encodeURIComponent(s.device)}&metric=${encodeURIComponent(s.metric)}&limit=120`);
    draw(card.querySelector('canvas'),pts);
  }
  $('alerts').innerHTML=al.length?al.map(a=>`<tr><td>${new Date(a.ts*1000).toLocaleTimeString()}</td>
    <td class="sev ${esc(a.severity)}">${a.severity==='critical'?'▲ ':'● '}${esc(a.severity)}</td><td>${esc(a.kind)}</td>
    <td>${esc(a.device)}/${esc(a.metric)}</td><td>${esc(a.message)}</td></tr>`).join('')
    :'<tr><td colspan="5">No alerts yet</td></tr>';
}
refresh();setInterval(refresh,2000);
</script></body></html>"""


def _clamp_int(text, default, lo, hi):
    try:
        return max(lo, min(hi, int(text)))
    except (TypeError, ValueError):
        return default


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console quiet
            pass

        def _send(self, code, body, ctype):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj), "application/json")

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if url.path == "/api/latest":
                return self._json(store.latest())
            if url.path == "/api/stats":
                return self._json(store.counts())
            if url.path == "/api/alerts":
                return self._json(store.alerts(_clamp_int(q.get("limit"), 50, 1, 500)))
            if url.path == "/api/series":
                device, metric = q.get("device", ""), q.get("metric", "")
                if not _NAME.match(device) or metric not in METRICS:
                    return self._json({"error": "device and metric are required and must be valid"}, 400)
                return self._json(store.series(device, metric, _clamp_int(q.get("limit"), 200, 1, 2000)))
            self._json({"error": "not found"}, 404)

    return Handler


def make_server(store, host="127.0.0.1", port=8000):
    return ThreadingHTTPServer((host, port), make_handler(store))
