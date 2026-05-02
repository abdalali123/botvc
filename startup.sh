#!/bin/bash
set -e

echo "[startup] ════════════════════════════════════════"
echo "[startup] Grok Audio Bridge - Initialization"
echo "[startup] ════════════════════════════════════════"

# ============ CLEANUP ============
echo "[startup] Cleaning PulseAudio environment..."
rm -rf /tmp/pulse* /var/run/pulse* /root/.config/pulse /home/pulse/.config/pulse 2>/dev/null || true
mkdir -p /tmp/pulse
chown -R pulse:pulse /tmp/pulse 2>/dev/null || true

# ============ PULSEAUDIO DAEMON STARTUP ============
echo "[startup] Starting PulseAudio daemon..."

# Run as root system daemon (avoids su permission issues)
# --daemonize=no keeps it in foreground so container doesn't exit
pulseaudio \
    --system \
    --disallow-exit \
    --exit-idle-time=-1 \
    --log-level=error \
    --log-target=syslog \
    --daemonize=no > /dev/null 2>&1 &

PA_PID=$!
echo "[startup] PulseAudio PID: $PA_PID"

# Wait for daemon to fully initialize
echo "[startup] Waiting for PulseAudio to initialize..."
MAX_WAIT=15
COUNTER=0

while [ $COUNTER -lt $MAX_WAIT ]; do
    if [ -S /tmp/pulse/native ]; then
        echo "[startup] PulseAudio socket ready ✓"
        break
    fi
    COUNTER=$((COUNTER + 1))
    echo "[startup] Waiting... ($COUNTER/$MAX_WAIT)"
    sleep 1
done

if [ ! -S /tmp/pulse/native ]; then
    echo "[startup] ERROR: PulseAudio socket not created after $MAX_WAIT seconds"
    echo "[startup] Check if PulseAudio daemon is running..."
    ps aux | grep -i pulse | grep -v grep || echo "PulseAudio process not found"
    exit 1
fi

# ============ VERIFY PULSEAUDIO ============
echo "[startup] Verifying PulseAudio connectivity..."
export PULSE_SERVER=unix:/tmp/pulse/native

if ! pactl info > /dev/null 2>&1; then
    echo "[startup] ERROR: Cannot connect to PulseAudio daemon"
    echo "[startup] Debugging info:"
    ls -la /tmp/pulse/ || echo "No /tmp/pulse directory"
    exit 1
fi

echo "[startup] PulseAudio verified ✓"

# ============ CONFIGURE AUDIO DEVICES ============
echo "[startup] Creating null sinks and audio devices..."

# Load null sink for Grok speaker output
pactl load-module module-null-sink \
    sink_name=grok_speaker \
    sink_properties="device.description='Grok Speaker'" 2>/dev/null || true

# Load null sink for Discord microphone input
pactl load-module module-null-sink \
    sink_name=discord_mic_sink \
    sink_properties="device.description='Discord Mic Source'" 2>/dev/null || true

# Remap the Discord sink monitor as an audio source
pactl load-module module-remap-source \
    master=discord_mic_sink.monitor \
    source_name=discord_mic \
    source_properties="device.description='Discord Mic Remapped'" 2>/dev/null || true

# Set default sink and source
pactl set-default-sink grok_speaker 2>/dev/null || true
pactl set-default-source discord_mic 2>/dev/null || true

echo "[startup] Audio devices configured ✓"

# ============ VERIFY AUDIO CONFIGURATION ============
echo "[startup] Verifying audio configuration..."

if pactl list sinks | grep -q "grok_speaker"; then
    echo "[startup]   ✓ grok_speaker sink ready"
else
    echo "[startup]   ✗ grok_speaker sink NOT found (critical!)"
fi

if pactl list sinks | grep -q "discord_mic_sink"; then
    echo "[startup]   ✓ discord_mic_sink ready"
else
    echo "[startup]   ✗ discord_mic_sink NOT found (critical!)"
fi

if pactl list sources | grep -q "discord_mic"; then
    echo "[startup]   ✓ discord_mic source ready"
else
    echo "[startup]   ✗ discord_mic source NOT found"
fi

# ============ LAUNCH PYTHON BOT ============
echo "[startup] ════════════════════════════════════════"
echo "[startup] Launching Python bot..."
echo "[startup] ════════════════════════════════════════"

cd /app
export PULSE_SERVER=unix:/tmp/pulse/native
export PYTHONUNBUFFERED=1

# Run bot (PID 1 replacement)
exec python main.py
