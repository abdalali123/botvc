FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    python3-dev \
    libffi-dev \
    libopus-dev \
    ffmpeg \
    pulseaudio \
    pulseaudio-utils \
    xvfb \
    libnss3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium
RUN playwright install-deps

COPY . .

RUN chmod +x startup.sh

# PulseAudio needs a home dir to write its socket
ENV HOME=/root
ENV PULSE_SERVER=unix:/run/user/0/pulse/native

CMD ["./startup.sh"]
