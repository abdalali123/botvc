FROM python:3.9-slim

# ============ INSTALL SYSTEM DEPENDENCIES ============
RUN apt-get update && apt-get install -y \
    git build-essential libffi-dev \
    libopus-dev libopus0 \
    libnss3 ca-certificates libxss1 libatk-bridge2.0-0 \
    libglib2.0-0 libgtk-3-0 libx11-xcb1 \
    curl wget \
    pulseaudio pulseaudio-utils \
    ffmpeg \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

# ============ NON-ROOT USER (PulseAudio refuses to run as root) ============
RUN useradd -m -s /bin/bash appuser \
    && usermod -aG audio appuser

# ============ PYTHON DEPENDENCIES ============
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ============ PLAYWRIGHT — install to a shared path accessible by appuser ============
# FIX: Without this, browsers land in /root/.cache which appuser cannot read at runtime.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN mkdir -p /ms-playwright \
    && playwright install chromium \
    && playwright install-deps \
    && chmod -R 755 /ms-playwright

# ============ PULSEAUDIO CLIENT CONFIG ============
# Tells appuser's PulseAudio client to connect to the system socket
# that startup.sh creates at /tmp/pulse/native.
RUN mkdir -p /etc/pulse && printf '%s\n' \
    'default-server = unix:/tmp/pulse/native' \
    'autospawn = no' \
    'daemon-binary = /bin/true' \
    'enable-shm = false' \
    > /etc/pulse/client.conf

# ============ COPY APPLICATION FILES ============
COPY main.py .
COPY startup.sh .
COPY cookies.jso[n] ./

RUN chmod +x startup.sh \
    && chown -R appuser:appuser /app \
    && mkdir -p /tmp/pulse \
    && chown appuser:appuser /tmp/pulse

# ============ ENVIRONMENT ============
ENV HOME=/home/appuser
ENV PYTHONUNBUFFERED=1
ENV PULSE_SERVER=unix:/tmp/pulse/native
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# ============ RUN AS NON-ROOT ============
USER appuser

CMD ["./startup.sh"]
