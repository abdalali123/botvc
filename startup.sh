#!/bin/bash
set -e

echo "[startup] Starting PulseAudio (non-system mode, allow-root=yes)..."

# Non-system mode uses PULSE_RUNTIME_PATH for its socket
export PULSE_RUNTIME_PATH=/tmp/pulse
mkdir -p /tmp/pulse

# No --system flag → no D-Bus dependency; daemon.conf has allow-root=yes
pulseaudio \
    --daemonize=yes \
    --exit-idle-time=-1 \
    --log-level=error

# Wait up to 10 s for the socket to appear
for i in $(seq 1 10); do
    [ -S /tmp/pulse/native ] && break
    echo "[startup] Waiting for PA socket... ($i/10)"
    sleep 1
done

if [ ! -S /tmp/pulse/native ]; then
    echo "[ERROR] PulseAudio socket never appeared. Check daemon.conf allow-root=yes"
    exit 1
fi

export PULSE_SERVER=unix:/tmp/pulse/native

echo "[startup] PulseAudio ready. Devices:"
pactl list short sinks
pactl list short sources

pactl set-default-sink   grok_speaker
pactl set-default-source discord_mic

echo "[startup] Launching bot..."
exec python main.py
