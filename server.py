# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""RedCar Pet SNS 서버 (stdlib만 사용).

정적 파일(web_sample.html 등) 서빙 + 좋아요/댓글 API.
  GET  /                  → web_sample.html
  GET  /api/engagement    → {source_key: {likes, comments[]}}
  POST /api/like          {key}          → {likes}
  POST /api/comment       {key,name,text} → {comment}
좋아요·댓글은 SQLite(db.py)에 저장되어 모든 접속자에게 공유된다.
실행: python server.py  (0.0.0.0:8000, LAN의 다른 기기에서 접속)
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import db

PORT = int(os.environ.get("PORT", "8000"))
ALLOWED = {"/web_sample.html", "/qr.png"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            path = "/web_sample.html"
        if path == "/api/engagement":
            return self._send(200, db.get_engagement())
        if path in ALLOWED:
            fp = os.path.join(config.OUTPUT_DIR, path.lstrip("/"))
            if os.path.isfile(fp):
                ctype = "text/html; charset=utf-8" if fp.endswith(".html") else "image/png"
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), ctype)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send(400, {"error": "bad json"})
        key = (body.get("key") or "").strip()
        if not key:
            return self._send(400, {"error": "key required"})
        if self.path == "/api/like":
            return self._send(200, {"likes": db.add_like(key)})
        if self.path == "/api/comment":
            c = db.add_comment(key, body.get("name"), body.get("text"))
            return self._send(200, {"comment": c} if c else {"error": "empty"})
        self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass  # 조용히


def main():
    db.init_db()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"RedCar Pet SNS 서버 시작: http://0.0.0.0:{PORT}  (DB: {db.DB_PATH})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
