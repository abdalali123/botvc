#!/bin/bash
set -e

echo "[startup] Starting PulseAudio daemon..."
pulseaudio --start --exit-idle-time=-1 --log-level=warn
sleep 1

echo "[startup] Creating virtual audio devices..."

# ── Virtual sink: Chromium plays Grok's voice here
pactl load-module module-null-sink \
    sink_name=grok_speaker \
    sink_properties=device.description="GrokSpeaker"

# ── Virtual sink used as backing for the fake Discord mic
pactl load-module module-null-sink \
    sink_name=discord_mic_sink \
    sink_properties=device.description="DiscordMicSink"

# ── Virtual source: Chromium reads Discord audio as its microphone
pactl load-module module-virtual-source \
    source_name=discord_mic \
    master=discord_mic_sink.monitor \
    source_properties=device.description="DiscordMic"

# Set defaults so Chromium picks them up automatically
pactl set-default-sink   grok_speaker
pactl set-default-source discord_mic

echo "[startup] PulseAudio devices ready:"
pactl list short sinks
pactl list short sources

echo "[startup] Launching bot..."
exec python main.py
