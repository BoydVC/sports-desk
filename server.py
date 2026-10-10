#!/usr/bin/env python3
"""Sports Desk server: serves web/, /api/desk (cached collect), /img/*. Refreshes in the background."""
import json
import os
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import collect

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = collect.CFG.get("port", 4244)
LOCK = threading.Lock()
STATE = {"desk": None, "error": None}


def refresh(force=False):
    with LOCK:
        try:
            STATE["desk"] = collect.collect(force=force)
            STATE["error"] = None
        except Exception as e:  # noqa: BLE001
            STATE["error"] = str(e)


def loop():
    while True:
        time.sleep(collect.CFG.get("refreshSeconds", 900))
        refresh()


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(HERE, "web"), **k)

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/health":
            return self._json({"ok": True, "generatedAt": (STATE["desk"] or {}).get("generatedAt"), "error": STATE["error"]})
        if p == "/api/desk":
            if "refresh=1" in self.path:
                refresh(force=True)
            if not STATE["desk"]:
                try:
                    STATE["desk"] = json.load(open(os.path.join(HERE, "data", "desk.json")))
                except Exception:  # noqa: BLE001
                    refresh()
            return self._json(STATE["desk"] or {"error": STATE["error"]})
        if p.startswith("/img/"):
            fn = os.path.basename(p)
            fp = os.path.join(HERE, "data", "img", fn)
            if not os.path.exists(fp):
                self.send_error(404)
                return
            ext = os.path.splitext(fn)[1].lower()
            ct = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/png")
            b = open(fp, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Cache-Control", "max-age=86400")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        return super().do_GET()


if __name__ == "__main__":
    try:
        STATE["desk"] = json.load(open(os.path.join(HERE, "data", "desk.json")))
    except Exception:  # noqa: BLE001
        pass
    threading.Thread(target=lambda: (refresh(), loop()), daemon=True).start()
    print(f"Sports Desk on http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
