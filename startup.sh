#!/bin/bash
set -e

echo "[startup] Starting PulseAudio (system mode, root)..."

# Modules are loaded by /etc/pulse/system.pa — no extra flags needed.
pulseaudio \
    --system \
    --daemonize=yes \
    --exit-idle-time=-1 \
    --log-level=error

# Wait for the socket to appear (max 10 s)
for i in $(seq 1 10); do
    [ -S /var/run/pulse/native ] && break
    echo "[startup] Waiting for PA socket... ($i/10)"
    sleep 1
done

[ -S /var/run/pulse/native ] || { echo "[ERROR] PulseAudio socket never appeared!"; exit 1; }

export PULSE_SERVER=unix:/var/run/pulse/native

echo "[startup] PulseAudio ready. Devices:"
pactl list short sinks
pactl list short sources

# Set defaults (modules are already loaded by system.pa)
pactl set-default-sink   grok_speaker
pactl set-default-source discord_mic

echo "[startup] Launching bot..."
exec python main.py
