#!/usr/bin/env bash
# Sports Desk: start in the background (idempotent).
#   ./run.sh            start (or report already running)
#   ./run.sh restart    stop and start fresh
#   ./run.sh stop       stop
#   ./run.sh build      collect + snapshot + PDF + screenshots + smoke test
cd "$(dirname "$0")"
PORT=$(python3 -c "import json;print(json.load(open('config.json')).get('port',4244))")
stop() { [ -f data/server.pid ] && kill "$(cat data/server.pid)" 2>/dev/null; rm -f data/server.pid; sleep 1; }
case "${1:-start}" in
  stop) stop; echo "Sports Desk stopped"; exit 0;;
  restart) stop;;
  build) python3 collect.py && python3 export_snapshot.py && ./render.sh && python3 tests/smoke_test.py; exit $?;;
esac
if curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  echo "Sports Desk already running: http://127.0.0.1:$PORT"; exit 0
fi
mkdir -p data
setsid nohup python3 server.py > data/server.log 2>&1 &
echo $! > data/server.pid
for i in $(seq 1 30); do curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break; sleep 0.5; done
echo "Sports Desk started (pid $(cat data/server.pid)): http://127.0.0.1:$PORT"
