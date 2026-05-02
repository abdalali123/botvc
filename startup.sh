#!/bin/bash
set -e

echo "[startup] Performing Deep Clean of PulseAudio remnants..."
# تنظيف شامل للمسارات لضمان عدم وجود ملفات قفل قديمة
rm -rf /tmp/pulse* /var/run/pulse* /root/.config/pulse /home/pulse/.config/pulse
mkdir -p /tmp/pulse
chown -R pulse:pulse /tmp/pulse

echo "[startup] Starting PulseAudio Service..."
# تشغيل PulseAudio بصلاحيات مستخدم pulse
su -s /bin/sh pulse -c "
    HOME=/home/pulse \
    PULSE_RUNTIME_PATH=/tmp/pulse \
    pulseaudio \
        --daemonize=yes \
        --exit-idle-time=-1 \
        --disallow-exit \
        --log-level=error
"

# التأكد من أن السوكيت (Socket) جاهز قبل المتابعة
MAX_WAIT=15
for i in $(seq 1 $MAX_WAIT); do
    if [ -S /tmp/pulse/native ]; then
        echo "[startup] PulseAudio socket found ✓"
        break
    fi
    echo "[startup] Waiting for audio socket... ($i/$MAX_WAIT)"
    sleep 1
done

echo "[startup] Configuring Audio Devices..."
# الحل الجذري: تنفيذ أوامر pactl باستخدام مستخدم pulse لتجنب Access Denied
su -s /bin/sh pulse -c "
    export PULSE_SERVER=unix:/tmp/pulse/native
    pactl load-module module-null-sink sink_name=grok_speaker sink_properties=device.description=Grok_Speaker
    pactl load-module module-null-sink sink_name=discord_mic_sink sink_properties=device.description=Discord_Mic_Source
    pactl load-module module-remap-source master=discord_mic_sink.monitor source_name=discord_mic source_properties=device.description=Discord_Mic_Remapped
    pactl set-default-sink grok_speaker
    pactl set-default-source discord_mic
"

echo "[startup] Launching Python Bot..."
# تشغيل البوت مع تمرير مسار السوكيت في البيئة
export PULSE_SERVER=unix:/tmp/pulse/native
exec python main.py
