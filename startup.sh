#!/bin/bash
set -e

echo "[startup] Starting PulseAudio as 'pulse' user..."

# تنظيف أي بقايا سابقة لمنع فشل التشغيل
mkdir -p /tmp/pulse
chown pulse:pulse /tmp/pulse
rm -f /tmp/pulse/native

# تشغيل PulseAudio بوضع المستخدم العادي لضمان تحميل الوحدات
su -s /bin/sh pulse -c "
    HOME=/home/pulse \
    PULSE_RUNTIME_PATH=/tmp/pulse \
    pulseaudio \
        --daemonize=yes \
        --exit-idle-time=-1 \
        --log-level=error
"

# الانتظار حتى يصبح الـ Socket جاهزاً
for i in $(seq 1 10); do
    [ -S /tmp/pulse/native ] && break
    echo "[startup] Waiting for PA socket... ($i/10)"
    sleep 1
done

if [ ! -S /tmp/pulse/native ]; then
    echo "[ERROR] PulseAudio socket never appeared!"
    exit 1
fi

# توحيد المسار ليراه البوت والمتصفح
export PULSE_SERVER=unix:/tmp/pulse/native

echo "[startup] PulseAudio ready. Configuring devices..."
# ضبط الأجهزة الافتراضية
pactl set-default-sink grok_speaker
pactl set-default-source discord_mic

echo "[startup] Launching bot..."
exec python main.py
