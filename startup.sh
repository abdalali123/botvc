#!/bin/bash
set -e

echo "[startup] Cleaning up old PulseAudio files..."
# تنظيف شامل لمنع فشل التشغيل
rm -rf /tmp/pulse* /var/run/pulse* /root/.config/pulse
mkdir -p /tmp/pulse
chown -R pulse:pulse /tmp/pulse

echo "[startup] Starting PulseAudio..."
# تشغيل PulseAudio مع تفعيل النظام المجهول ومنع تحميل الوحدات التي قد تسبب تعارض في الحاويات
su -s /bin/sh pulse -c "
    HOME=/home/pulse \
    PULSE_RUNTIME_PATH=/tmp/pulse \
    pulseaudio \
        --daemonize=yes \
        --exit-idle-time=-1 \
        --disallow-exit \
        --disallow-module-loading=no \
        --log-level=error
"

# الانتظار والتأكد من وجود السوكيت
MAX_RETRIES=15
for i in $(seq 1 $MAX_RETRIES); do
    if [ -S /tmp/pulse/native ]; then
        echo "[startup] PulseAudio socket found ✓"
        break
    fi
    echo "[startup] Waiting for PA socket... ($i/$MAX_RETRIES)"
    sleep 1
    if [ $i -eq $MAX_RETRIES ]; then
        echo "[ERROR] PulseAudio failed to start."
        exit 1
    fi
done

echo "[startup] Configuring Audio Devices..."
pactl load-module module-null-sink sink_name=grok_speaker sink_properties=device.description=Grok_Speaker
pactl load-module module-null-sink sink_name=discord_mic_sink sink_properties=device.description=Discord_Mic_Source
pactl load-module module-remap-source master=discord_mic_sink.monitor source_name=discord_mic source_properties=device.description=Discord_Mic_Remapped

pactl set-default-sink grok_speaker
pactl set-default-source discord_mic

echo "[startup] Launching Bot..."
exec python main.py
