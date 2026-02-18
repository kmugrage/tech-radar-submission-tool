#!/usr/bin/env bash
# server.sh — start and stop the Tech Radar blip submission tool
set -euo pipefail

PORT=8000
PID_FILE=".server.pid"
LOG_FILE=".server.log"
PYTHON=".venv/bin/python"

_check_venv() {
  if [[ ! -f "$PYTHON" ]]; then
    echo "Error: virtual environment not found. Run 'make setup' first." >&2
    exit 1
  fi
}

_is_running() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

start() {
  _check_venv

  if _is_running; then
    echo "Server is already running (PID $(cat "$PID_FILE")). Use '$0 stop' to stop it."
    exit 1
  fi

  local dev_mode=""
  if [[ "${1:-}" == "--dev" ]]; then
    dev_mode="DEV_MODE=true "
    echo "Starting in dev mode (mock responses, no API key needed)..."
  else
    echo "Starting server (requires ANTHROPIC_API_KEY)..."
  fi

  eval "${dev_mode}$PYTHON -m uvicorn app.main:app \
    --host 0.0.0.0 --port $PORT --reload" \
    > "$LOG_FILE" 2>&1 &

  echo $! > "$PID_FILE"
  sleep 1  # give uvicorn a moment to bind

  if _is_running; then
    echo "Server started on http://localhost:$PORT (PID $(cat "$PID_FILE"))"
    echo "Logs: $LOG_FILE  (tail -f $LOG_FILE to follow)"
  else
    echo "Server failed to start. Check $LOG_FILE for details." >&2
    rm -f "$PID_FILE"
    exit 1
  fi
}

stop() {
  if ! _is_running; then
    echo "Server is not running."
    rm -f "$PID_FILE"
    exit 0
  fi

  local pid
  pid=$(cat "$PID_FILE")
  echo "Stopping server (PID $pid)..."
  kill "$pid"
  rm -f "$PID_FILE"
  echo "Server stopped."
}

status() {
  if _is_running; then
    echo "Server is running (PID $(cat "$PID_FILE")) on http://localhost:$PORT"
  else
    echo "Server is not running."
    [[ -f "$PID_FILE" ]] && rm -f "$PID_FILE"
    return 0
  fi
}

usage() {
  echo "Usage: $0 {start [--dev] | stop | status}"
  echo ""
  echo "  start          Start the server (requires ANTHROPIC_API_KEY)"
  echo "  start --dev    Start in dev mode (mock responses, no API key needed)"
  echo "  stop           Stop the server"
  echo "  status         Show whether the server is running"
}

case "${1:-}" in
  start)  start "${2:-}" ;;
  stop)   stop ;;
  status) status ;;
  *)      usage; exit 1 ;;
esac
