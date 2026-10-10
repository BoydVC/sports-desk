#!/usr/bin/env bash
# Screenshots (1440x900 desktop + full page, 390x844 phone) and printable PDF via headless Chrome.
cd "$(dirname "$0")"
PORT=$(python3 -c "import json;print(json.load(open('config.json')).get('port',4244))")
URL=${URL:-"http://127.0.0.1:$PORT/"}
SNAP="file://$PWD/dist/sports-desk-snapshot.html"
C="google-chrome --headless=new --no-sandbox --disable-gpu --hide-scrollbars --run-all-compositor-stages-before-draw --virtual-time-budget=${BUDGET:-8000}"
shot() { local name=$1 w=$2 h=$3 url=$4 scale=${5:-1}; local d=/tmp/sd-chrome-$$-$name
  $C --force-device-scale-factor=$scale --window-size=$w,$h --user-data-dir=$d --screenshot="screenshots/$name.png" "$url" 2>/dev/null; rm -rf $d; ls -la screenshots/$name.png; }
mkdir -p screenshots dist
shot desktop-1440x900 1440 900 "$URL"
shot desktop-1440-full 1440 ${FULLH:-3300} "$URL"
shot phone-390x844 390 844 "$URL" 2
shot phone-390-full 390 ${PHONEH:-7400} "$URL" 2
d=/tmp/sd-chrome-$$-pdf
$C --user-data-dir=$d --no-pdf-header-footer --print-to-pdf="dist/sports-desk.pdf" "$SNAP" 2>/dev/null; rm -rf $d
ls -la dist/sports-desk.pdf
