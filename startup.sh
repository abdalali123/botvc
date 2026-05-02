#!/bin/bash
set -e

echo "[startup] ════════════════════════════════════════"
echo "[startup] Grok Audio Bridge - Initialization"
echo "[startup] ════════════════════════════════════════"

# ============ SINGLE INSTANCE GUARD ============
# Prevents the "Unknown Interaction" (10062) error caused by two bots
# connecting simultaneously with the same Discord token.
LOCKFILE=/tmp/grok_bot.lock
if [ -f "$LOCKFILE" ]; then
    PID=$(cat "$LOCKFILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[startup] ERROR: Another instance is already running (PID $PID). Exiting."
        exit 1
    else
        echo "[startup] Stale lock file found. Removing."
        rm -f "$LOCKFILE"
    fi
fi
echo $$ > "$LOCKFILE"
trap "rm -f $LOCKFILE" EXIT

# ============ PULSEAUDIO SETUP ============
echo "[startup] Setting up PulseAudio..."
mkdir -p /tmp/pulse

# Kill any stale PulseAudio daemon from a previous crashed run
pulseaudio --kill 2>/dev/null || true
sleep 1

# Start PulseAudio in user-daemon mode
pulseaudio \
    --start \
    --exit-idle-time=-1 \
    --daemonize=yes \
    --log-target=stderr 2>/dev/null

# Wait for PulseAudio socket to be ready (up to 5 seconds)
PULSE_READY=0
for i in $(seq 1 10); do
    if pactl info >/dev/null 2>&1; then
        echo "[startup] PulseAudio running ✓"
        PULSE_READY=1
        break
    fi
    sleep 0.5
done

if [ "$PULSE_READY" -eq 0 ]; then
    echo "[startup] WARNING: PulseAudio did not start — audio bridges will be unavailable"
fi

# ============ CREATE VIRTUAL AUDIO DEVICES ============
echo "[startup] Creating audio devices..."

# grok_speaker: Chromium outputs Grok's voice here → FFmpeg reads its .monitor → Discord
pactl load-module module-null-sink \
    sink_name=grok_speaker \
    sink_properties=device.description=GrokSpeaker 2>/dev/null \
    && echo "[startup] grok_speaker sink created ✓" \
    || echo "[startup] Note: grok_speaker sink not available"

# discord_mic_sink: We write Discord audio here → Chromium reads discord_mic as a mic
pactl load-module module-null-sink \
    sink_name=discord_mic_sink \
    sink_properties=device.description=DiscordMicSink 2>/dev/null \
    && echo "[startup] discord_mic_sink created ✓" \
    || echo "[startup] Note: discord_mic_sink not available"

# discord_mic: a virtual source (microphone) backed by discord_mic_sink.monitor
pactl load-module module-remap-source \
    master=discord_mic_sink.monitor \
    source_name=discord_mic \
    source_properties=device.description=DiscordMic 2>/dev/null \
    && echo "[startup] discord_mic remapping created ✓" \
    || echo "[startup] Note: discord_mic remapping not available"

echo "[startup] Audio setup complete"

# ============ LAUNCH BOT ============
cd /app
export PYTHONUNBUFFERED=1
# Tell Chromium to output to grok_speaker so we can capture it
export PULSE_SINK=grok_speaker

echo "[startup] Launching bot..."
exec python main.py
