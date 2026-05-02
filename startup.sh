#!/bin/bash
set -e

echo "[startup] Starting PulseAudio as 'pulse' user..."

# PulseAudio won't run as root in non-system mode.
# Run it as the dedicated 'pulse' user; auth-anonymous=1 in default.pa
# lets the root bot process connect to the socket without a cookie.
mkdir -p /tmp/pulse
chown pulse:pulse /tmp/pulse

su -s /bin/sh pulse -c "
    HOME=/home/pulse \
    PULSE_RUNTIME_PATH=/tmp/pulse \
    pulseaudio \
        --daemonize=yes \
        --exit-idle-time=-1 \
        --log-level=error
"

# Wait up to 10 s for the socket
for i in $(seq 1 10); do
    [ -S /tmp/pulse/native ] && break
    echo "[startup] Waiting for PA socket... ($i/10)"
    sleep 1
done

if [ ! -S /tmp/pulse/native ]; then
    echo "[ERROR] PulseAudio socket never appeared!"
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
