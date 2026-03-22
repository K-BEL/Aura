#!/bin/bash
# Test ASR by recording your voice from the microphone
# Usage: bash test_asr.sh [port]
#
# Requires: sox (brew install sox) or ffmpeg

ASR_PORT="${1:-8080}"
ASR_URL="http://localhost:${ASR_PORT}"
DIR="$(cd "$(dirname "$0")" && pwd)"
RECORDING="$DIR/mic_recording.wav"

echo ""
echo "🎙️  ASR Live Mic Test — Qwen3-ASR-1.7B"
echo "========================================"
echo ""

# Health check
echo "🔍 Checking server at $ASR_URL ..."
HEALTH=$(curl -s --max-time 5 "$ASR_URL/health")
if [ -z "$HEALTH" ]; then
  echo "❌ Server not reachable at $ASR_URL"
  echo "   Make sure SSH tunnel and server are running."
  exit 1
fi
echo "✅ Server online"
echo ""

# Detect recording tool
if command -v sox &> /dev/null || command -v rec &> /dev/null; then
  RECORD_CMD="rec"
elif command -v ffmpeg &> /dev/null; then
  RECORD_CMD="ffmpeg"
else
  echo "❌ No recording tool found."
  echo "   Install sox:    brew install sox"
  echo "   Or ffmpeg:      brew install ffmpeg"
  exit 1
fi

# Record loop
while true; do
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🎤 Press ENTER to start recording..."
  echo "   (type 'q' + ENTER to quit)"
  read -r CMD
  if [ "$CMD" = "q" ]; then
    echo "👋 Bye!"
    exit 0
  fi

  echo "🔴 RECORDING... Press Ctrl+C to stop"
  echo ""

  # Record audio
  if [ "$RECORD_CMD" = "rec" ]; then
    rec -q -r 16000 -c 1 -b 16 "$RECORDING" 2>/dev/null
  else
    ffmpeg -y -f avfoundation -i ":0" -ar 16000 -ac 1 -t 30 "$RECORDING" -loglevel quiet 2>/dev/null
  fi

  SIZE=$(wc -c < "$RECORDING" 2>/dev/null | tr -d ' ')
  if [ -z "$SIZE" ] || [ "$SIZE" -lt 500 ]; then
    echo "⚠️  Recording too short or empty. Try again."
    echo ""
    continue
  fi
  echo ""
  echo "✅ Recorded $SIZE bytes"

  # Transcribe
  echo "⏳ Transcribing..."
  RESULT=$(curl -s -X POST "$ASR_URL/asr/transcribe" \
    -F "audio=@${RECORDING}" \
    --max-time 120)

  echo ""
  echo "📝 Result: $RESULT"
  echo ""
done
