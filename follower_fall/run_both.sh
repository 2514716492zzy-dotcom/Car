#!/usr/bin/env bash
set -euo pipefail

# Run both pipelines in parallel:
# 1) vision follow controller
# 2) voice assistant

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

FOLLOW_LOG="$LOG_DIR/follow.log"
VOICE_LOG="$LOG_DIR/voice.log"

CONDA_ENV="${1:-car_detector}"

if ! command -v conda >/dev/null 2>&1; then
  echo "[ERROR] conda command not found in PATH."
  exit 1
fi

echo "[INFO] Using conda env: $CONDA_ENV"

echo "[INFO] Starting follow script..."
conda run --no-capture-output -n "$CONDA_ENV" \
  python3 "$ROOT_DIR/test_FB_first.py" 2>&1 \
  | stdbuf -oL awk '{print "[FOLLOW] " $0; fflush();}' \
  | tee -a "$FOLLOW_LOG" &
FOLLOW_PID=$!
echo "[INFO] follow stream PID: $FOLLOW_PID (log: $FOLLOW_LOG)"

echo "[INFO] Starting voice script..."
conda run --no-capture-output -n "$CONDA_ENV" \
  python3 "$ROOT_DIR/voice_llm_speaker.py" \
  --player mpg123 \
  --linux-speaker-device hw:2,0 2>&1 \
  | stdbuf -oL awk '{print "[SPEAK] " $0; fflush();}' \
  | tee -a "$VOICE_LOG" &
VOICE_PID=$!
echo "[INFO] voice stream PID: $VOICE_PID (log: $VOICE_LOG)"

cleanup() {
  echo
  echo "[INFO] Stopping child processes..."
  kill "$FOLLOW_PID" "$VOICE_PID" 2>/dev/null || true
  wait "$FOLLOW_PID" "$VOICE_PID" 2>/dev/null || true
  echo "[INFO] Stopped."
}
trap cleanup INT TERM EXIT

echo "[INFO] Both services are running. Press Ctrl+C to stop both."
wait "$FOLLOW_PID" "$VOICE_PID"
