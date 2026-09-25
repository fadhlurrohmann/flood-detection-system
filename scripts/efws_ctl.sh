#!/usr/bin/env bash
# ============================================================
#  EFWS — Script control process (start/stop/restart/status/logs)
#  Use this for testing manual WITHOUT systemd (more fast for
#  iterasi sambil prototyping). For production, use systemd
#  (efws.service) because auto-start when boot & auto-restart when crash.
#
#  Place file this in:  <root-project>/scripts/efws_ctl.sh
#  Structure project this FLAT - main.py exists directly in root project
#  (sejajar with folder venv/, .env, scripts/, run/).
#
#  Usage:
#    ./scripts/efws_ctl.sh start
#    ./scripts/efws_ctl.sh stop
#    ./scripts/efws_ctl.sh restart      <- run every time update code
#    ./scripts/efws_ctl.sh status
#    ./scripts/efws_ctl.sh logs
# ============================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"
PID_FILE="$PROJECT_ROOT/run/efws.pid"
STDOUT_LOG="$PROJECT_ROOT/run/efws_stdout.log"

mkdir -p "$(dirname "$PID_FILE")"

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

start() {
    if is_running; then
        echo "EFWS already running (PID $(cat "$PID_FILE"))."
        return 0
    fi
    if [ ! -x "$VENV_PYTHON" ]; then
        echo "ERROR: venv python not found in $VENV_PYTHON"
        echo "Run first: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        echo "ERROR: .env not found in $PROJECT_ROOT/.env"
        echo "Run first: cp .env.example .env  then content EFWS_API_URL"
        exit 1
    fi
    echo "Starting EFWS..."
    cd "$PROJECT_ROOT"
    nohup "$VENV_PYTHON" main.py >> "$STDOUT_LOG" 2>&1 &
    echo $! > "$PID_FILE"
    disown
    sleep 1.5
    if is_running; then
        echo "EFWS started (PID $(cat "$PID_FILE")). Log: tail -f $PROJECT_ROOT/logs/efws.log"
    else
        echo "EFWS FAILED start - check content: $STDOUT_LOG"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop() {
    if ! is_running; then
        echo "EFWS not medium running."
        rm -f "$PID_FILE"
        return 0
    fi
    PID=$(cat "$PID_FILE")
    echo "Stopping EFWS (PID $PID)..."
    kill "$PID"
    for i in $(seq 1 10); do
        if ! kill -0 "$PID" 2>/dev/null; then break; fi
        sleep 1
    done
    if kill -0 "$PID" 2>/dev/null; then
        echo "Not yet stop, force kill..."
        kill -9 "$PID"
    fi
    rm -f "$PID_FILE"
    echo "EFWS stopped."
}

restart() {
    echo "=== Restarting EFWS (use this each time update code) ==="
    stop
    sleep 1
    start
}

status() {
    if is_running; then
        echo "EFWS medium RUNNING (PID $(cat "$PID_FILE"))."
        ps -p "$(cat "$PID_FILE")" -o pid,etime,%cpu,%mem,cmd 2>/dev/null
    else
        echo "EFWS NOT running."
    fi
}

logs() {
    echo "Tail logs/efws.log (Ctrl+C for stop memantau - process STILL running):"
    tail -f "$PROJECT_ROOT/logs/efws.log"
}

case "${1:-}" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    logs)    logs ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
