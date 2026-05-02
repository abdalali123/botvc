FROM python:3.9-slim

# ============ INSTALL SYSTEM DEPENDENCIES ============
RUN apt-get update && apt-get install -y \
    # Build tools
    git build-essential libffi-dev \
    # Opus codec (runtime + dev)
    libopus-dev libopus0 \
    # Chromium / Playwright dependencies
    libnss3 ca-certificates libxss1 libatk-bridge2.0-0 \
    libglib2.0-0 libgtk-3-0 libx11-xcb1 \
    curl wget \
    # PulseAudio (daemon + pacat utility for piping PCM)
    pulseaudio pulseaudio-utils \
    # FFmpeg (for reading PulseAudio monitor → Discord)
    ffmpeg \
    # ALSA utils (helpful for debugging audio)
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

# ============ NON-ROOT USER (PulseAudio refuses to run as root) ============
RUN useradd -m -s /bin/bash appuser \
    && usermod -aG audio appuser

# ============ PYTHON DEPENDENCIES ============
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright's Chromium browser
RUN playwright install chromium
RUN playwright install-deps

# ============ COPY APPLICATION FILES ============
COPY main.py .
COPY startup.sh .
# cookies.json is optional — copy it only if it exists
COPY cookies.jso[n] ./

# Fix permissions
RUN chmod +x startup.sh \
    && chown -R appuser:appuser /app \
    && mkdir -p /tmp/pulse \
    && chown appuser:appuser /tmp/pulse

# ============ ENVIRONMENT ============
ENV HOME=/home/appuser
ENV PYTHONUNBUFFERED=1
ENV PULSE_SERVER=unix:/tmp/pulse/native

# ============ RUN AS NON-ROOT ============
USER appuser

CMD ["./startup.sh"]
