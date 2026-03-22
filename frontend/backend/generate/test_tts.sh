#!/bin/bash
# Test TTS generation via SSH tunnel
# Usage: bash test_tts.sh [port]

TTS_PORT="${1:-8080}"
TTS_URL="http://localhost:${TTS_PORT}"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "🔍 Checking TTS server at $TTS_URL ..."
HEALTH=$(curl -s --max-time 5 "$TTS_URL/health")
if [ -z "$HEALTH" ]; then
  echo "❌ Server not reachable at $TTS_URL"
  echo "   Make sure SSH tunnel and TTS server are running."
  exit 1
fi
echo "Health: $HEALTH"
echo ""

# Test 1: Orion voice
echo "🎤 Test 1: Generating speech with voice=orion ..."
curl -s -X POST "$TTS_URL/tts/generate" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello! This is the orion voice speaking from the cloud GPU.","voice":"orion"}' \
  -o "$DIR/test_orion.wav" --max-time 120
SIZE=$(wc -c < "$DIR/test_orion.wav" | tr -d ' ')
echo "  → Saved to $DIR/test_orion.wav ($SIZE bytes)"

# Test 2: Nova voice
echo "🎤 Test 2: Generating speech with voice=nova ..."
curl -s -X POST "$TTS_URL/tts/generate" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hi there! I am the nova voice, running on a remote GPU.","voice":"nova"}' \
  -o "$DIR/test_nova.wav" --max-time 120
SIZE=$(wc -c < "$DIR/test_nova.wav" | tr -d ' ')
echo "  → Saved to $DIR/test_nova.wav ($SIZE bytes)"

echo ""
echo "✅ Done! Valid files should be 400KB-800KB."
echo "   Play them with:"
echo "   open $DIR/test_orion.wav"
echo "   open $DIR/test_nova.wav"
