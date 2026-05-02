#!/bin/bash
set -e

echo "[startup] Starting PulseAudio in system mode (running as root)..."

# Root requires --system. Create the runtime socket dir first.
mkdir -p /var/run/pulse

pulseaudio \
    --system \
    --daemonize=yes \
    --exit-idle-time=-1 \
    --log-level=warn \
    --disallow-exit \
    --disallow-module-loading=no

# Give PA time to fully initialise
sleep 2

# Point every client at the system socket
export PULSE_SERVER=unix:/var/run/pulse/native

echo "[startup] Verifying PulseAudio is alive..."
pactl info | grep "Server Name" || { echo "[ERROR] PulseAudio failed to start!"; exit 1; }

echo "[startup] Creating virtual audio devices..."

pactl load-module module-null-sink \
    sink_name=grok_speaker \
    sink_properties=device.description="GrokSpeaker"

pactl load-module module-null-sink \
    sink_name=discord_mic_sink \
    sink_properties=device.description="DiscordMicSink"

pactl load-module module-virtual-source \
    source_name=discord_mic \
    master=discord_mic_sink.monitor \
    source_properties=device.description="DiscordMic"

pactl set-default-sink   grok_speaker
pactl set-default-source discord_mic

echo "[startup] PulseAudio devices:"
pactl list short sinks
pactl list short sources

echo "[startup] Launching bot..."
exec python main.py
