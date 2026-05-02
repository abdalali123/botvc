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

# Create minimal PulseAudio config for user mode
cat > /root/.config/pulse/daemon.conf << 'EOF'
daemonize = no
log-level = error
log-target = stderr
exit-idle-time = -1
disallow-exit = yes
load-default-script = yes
EOF

# Start PulseAudio in user mode (more reliable in containers)
export PULSE_RUNTIME_PATH=/tmp/pulse
export PULSE_SERVER=unix:/tmp/pulse/native

pulseaudio --start --verbose 2>&1 &
PA_PID=$!

# Wait for socket
echo "[startup] Waiting for PulseAudio socket..."
for i in {1..15}; do
    if [ -S /tmp/pulse/native ]; then
        echo "[startup] PulseAudio ready ✓"
        sleep 1
        break
    fi
    sleep 1
done

if [ ! -S /tmp/pulse/native ]; then
    echo "[startup] ERROR: PulseAudio socket not created"
    killall pulseaudio 2>/dev/null || true
    exit 1
fi

# ============ CONFIGURE AUDIO DEVICES ============
echo "[startup] Creating audio devices..."

# Create null sinks
pactl load-module module-null-sink sink_name=grok_speaker sink_properties="device.description='Grok Speaker'" 2>/dev/null || true
pactl load-module module-null-sink sink_name=discord_mic_sink sink_properties="device.description='Discord Mic'" 2>/dev/null || true
pactl load-module module-remap-source master=discord_mic_sink.monitor source_name=discord_mic source_properties="device.description='Discord Mic'" 2>/dev/null || true

pactl set-default-sink grok_speaker 2>/dev/null || true
pactl set-default-source discord_mic 2>/dev/null || true

echo "[startup] Audio configured ✓"

# ============ LAUNCH PYTHON BOT ============
cd /app
export PULSE_SERVER=unix:/tmp/pulse/native
export PYTHONUNBUFFERED=1

echo "[startup] Launching bot..."
exec python main.py
