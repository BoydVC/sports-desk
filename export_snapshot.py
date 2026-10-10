#!/usr/bin/env python3
"""Bundle the page into one offline file: dist/sports-desk-snapshot.html
(CSS, fonts, JS, data and every cached image inlined; links to sources stay live)."""
import base64
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, "web")


def b64(path, mime):
    return f"data:{mime};base64," + base64.b64encode(open(path, "rb").read()).decode()


def img_uri(local):
    fp = os.path.join(HERE, "data", "img", os.path.basename(local))
    if not os.path.exists(fp):
        return None
    ext = os.path.splitext(fp)[1].lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/png")
    return b64(fp, mime)


def inline_images(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if isinstance(v, str) and v.startswith("/img/"):
                out[k] = img_uri(v)
            else:
                out[k] = inline_images(v)
        # never hotlink in the offline file: drop remote image URLs that have a local twin or none
        for k in list(out):
            if k in ("logo", "oppLogo", "image") and isinstance(out[k], str) and out[k].startswith("http"):
                out[k] = None
        return out
    if isinstance(o, list):
        return [inline_images(x) for x in o]
    return o


def main():
    desk = json.load(open(os.path.join(HERE, "data", "desk.json")))
    desk = inline_images(desk)
    css = open(os.path.join(W, "style.css")).read()
    css = re.sub(r"url\(fonts/([^)]+)\)", lambda m: f"url({b64(os.path.join(W, 'fonts', m.group(1)), 'font/ttf')})", css)
    js = open(os.path.join(W, "app.js")).read()
    html = open(os.path.join(W, "index.html")).read()
    html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>{css}</style>")
    data = json.dumps(desk, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace('<script src="app.js"></script>', f"<script>window.DESK={data};</script>\n<script>{js}</script>")
    html = html.replace("<title>The Sports Desk · Boyd Edition</title>", f"<title>The Sports Desk · {desk.get('generatedAtEt', '')}</title>")
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", "sports-desk-snapshot.html")
    open(out, "w").write(html)
    print(out, f"{os.path.getsize(out) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
