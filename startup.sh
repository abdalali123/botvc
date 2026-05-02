#!/bin/bash
set -e

echo "[startup] Starting PulseAudio..."

# تنظيف المسارات القديمة
mkdir -p /tmp/pulse
chown pulse:pulse /tmp/pulse
rm -f /tmp/pulse/native

# تشغيل PulseAudio في الخلفية
su -s /bin/sh pulse -c "
    HOME=/home/pulse \
    PULSE_RUNTIME_PATH=/tmp/pulse \
    pulseaudio \
        --daemonize=yes \
        --exit-idle-time=-1 \
        --disallow-exit \
        --log-level=error
"

# الانتظار حتى يعمل السوكيت
for i in $(seq 1 10); do
    [ -S /tmp/pulse/native ] && break
    echo "[startup] Waiting for PA socket... ($i/10)"
    sleep 1
done

echo "[startup] Configuring Null-Sinks..."
# إنشاء سماعة وهمية لـ Grok
pactl load-module module-null-sink sink_name=grok_speaker sink_properties=device.description=Grok_Speaker
# إنشاء ميكروفون وهمي لـ Grok (ليسمع صوتك من ديسكورد)
pactl load-module module-null-sink sink_name=discord_mic_sink sink_properties=device.description=Discord_Mic_Source
pactl load-module module-remap-source master=discord_mic_sink.monitor source_name=discord_mic source_properties=device.description=Discord_Mic_Remapped

# ضبط الأجهزة الافتراضية
pactl set-default-sink grok_speaker
pactl set-default-source discord_mic

echo "[startup] Starting Python Bot..."
exec python main.py
