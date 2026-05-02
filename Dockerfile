FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    git build-essential python3-dev libffi-dev libopus-dev \
    ffmpeg pulseaudio xvfb libnss3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium
RUN playwright install-deps

COPY . .

# إنشاء Sink لسماع Grok و Source لإطعام Grok صوت المستخدم
CMD pulseaudio -D --exit-idle-time=-1 --system --disallow-exit && \
    pactl load-module module-null-sink sink_name=grok_output sink_properties=device.description="Grok_Output" && \
    pactl load-module module-null-sink sink_name=user_voice_to_grok sink_properties=device.description="User_Voice_To_Grok" && \
    python main.py
