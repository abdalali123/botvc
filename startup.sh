#!/bin/bash
set -e

echo "[startup] ════════════════════════════════════════"
echo "[startup] Grok Audio Bridge - Initialization"
echo "[startup] ════════════════════════════════════════"

# ============ SETUP PULSEAUDIO IN USER MODE ============
echo "[startup] Setting up PulseAudio..."

# Create PulseAudio config directory
mkdir -p /root/.config/pulse
mkdir -p /tmp/pulse

# Start PulseAudio in user mode
export PULSE_RUNTIME_PATH=/tmp/pulse
export PULSE_SERVER=unix:/tmp/pulse/native

# Start with minimal config
pulseaudio --start -D 2>&1 || true
sleep 2

# Check if socket was created
if [ ! -S /tmp/pulse/native ]; then
    echo "[startup] WARNING: PulseAudio socket not available, continuing without it..."
else
    echo "[startup] PulseAudio ready ✓"
fi

# ============ CONFIGURE AUDIO DEVICES ============
echo "[startup] Creating audio devices..."

# Try to create null sinks (these will fail gracefully if PulseAudio isn't ready)
pactl load-module module-null-sink sink_name=grok_speaker sink_properties="device.description='Grok Speaker'" 2>/dev/null || echo "[startup] Note: grok_speaker sink not available"
pactl load-module module-null-sink sink_name=discord_mic_sink sink_properties="device.description='Discord Mic'" 2>/dev/null || echo "[startup] Note: discord_mic_sink not available"
pactl load-module module-remap-source master=discord_mic_sink.monitor source_name=discord_mic source_properties="device.description='Discord Mic'" 2>/dev/null || echo "[startup] Note: discord_mic remapping not available"

pactl set-default-sink grok_speaker 2>/dev/null || true
pactl set-default-source discord_mic 2>/dev/null || true

echo "[startup] Audio setup complete"

# ============ LAUNCH PYTHON BOT ============
cd /app
export PULSE_SERVER=unix:/tmp/pulse/native
export PYTHONUNBUFFERED=1

echo "[startup] Launching bot..."
exec python main.py
