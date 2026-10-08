#!/usr/bin/env bash
# ============================================================
#  EFWS — Process control script (start/stop/restart/status/logs)
#  Use this for manual testing WITHOUT systemd (faster for
#  iterating while prototyping). For production, use systemd
#  (efws.service) because it auto-starts at boot & auto-restarts on a crash.
#
#  Put this file at:  <project-root>/scripts/efws_ctl.sh
#  This project's structure is FLAT - main.py is directly in the project root
#  (alongside the venv/, .env, scripts/, run/ folders).
#
#  Usage:
#    ./scripts/efws_ctl.sh start
#    ./scripts/efws_ctl.sh stop
#    ./scripts/efws_ctl.sh restart      <- run this every time you update the code
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
        echo "EFWS is already running (PID $(cat "$PID_FILE"))."
        return 0
    fi
    if [ ! -x "$VENV_PYTHON" ]; then
        echo "ERROR: venv python not found at $VENV_PYTHON"
        echo "Run this first: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        echo "ERROR: .env not found at $PROJECT_ROOT/.env"
        echo "Run this first: cp .env.example .env  then fill in EFWS_API_URL"
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
        echo "EFWS FAILED to start - check the contents of: $STDOUT_LOG"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop() {
    if ! is_running; then
        echo "EFWS is not running."
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
        echo "Not stopped yet, force kill..."
        kill -9 "$PID"
    fi
    rm -f "$PID_FILE"
    echo "EFWS stopped."
}

restart() {
    echo "=== Restarting EFWS (use this every time you update the code) ==="
    stop
    sleep 1
    start
}

status() {
    if is_running; then
        echo "EFWS is RUNNING (PID $(cat "$PID_FILE"))."
        ps -p "$(cat "$PID_FILE")" -o pid,etime,%cpu,%mem,cmd 2>/dev/null
    else
        echo "EFWS is NOT running."
    fi
}

logs() {
    echo "Tail logs/efws.log (Ctrl+C to stop watching - the process KEEPS running):"
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
