FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    git build-essential libffi-dev libopus-dev \
    ffmpeg pulseaudio pulseaudio-utils xvfb libnss3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# إصلاح صلاحيات مستخدم pulse
RUN if ! id -u pulse > /dev/null 2>&1; then useradd -m -r pulse; fi \
    && mkdir -p /tmp/pulse /home/pulse \
    && chown -R pulse:pulse /tmp/pulse /home/pulse

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium && playwright install-deps

COPY . .
RUN chmod +x startup.sh

ENV PULSE_SERVER=unix:/tmp/pulse/native
ENV HOME=/root

CMD ["./startup.sh"]
