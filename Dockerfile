FROM python:3.9-slim

# ── System packages ───────────────────────────────────────────────────────────
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

# ── Allow PulseAudio system-mode socket dir ───────────────────────────────────
RUN mkdir -p /var/run/pulse && chmod 755 /var/run/pulse

WORKDIR /app

# ── Python deps ───────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright: pin the browser cache to a fixed path used at runtime ─────────
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium
RUN playwright install-deps

# ── App files ─────────────────────────────────────────────────────────────────
COPY . .
RUN chmod +x startup.sh

# PulseAudio system socket — inherited by Python and Chromium
ENV PULSE_SERVER=unix:/var/run/pulse/native
ENV HOME=/root

CMD ["./startup.sh"]
