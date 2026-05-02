FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    git build-essential python3-dev libffi-dev libopus-dev \
    ffmpeg pulseaudio pulseaudio-utils xvfb libnss3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# إعداد مستخدم PulseAudio
RUN useradd -m -r pulse && mkdir -p /tmp/pulse && chown -R pulse:pulse /tmp/pulse

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium && playwright install-deps

COPY . .
RUN chmod +x startup.sh

# المسار الموحد للاتصال الصوتي
ENV PULSE_SERVER=unix:/tmp/pulse/native
ENV HOME=/root

CMD ["./startup.sh"]
