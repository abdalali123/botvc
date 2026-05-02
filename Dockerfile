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

# ── PulseAudio: non-system mode, allow root ──────────────────────────────────
RUN mkdir -p /etc/pulse /tmp/pulse

# Allow PA to start as root without --system (avoids D-Bus dependency)
RUN echo "allow-root = yes" >> /etc/pulse/daemon.conf

# Minimal default.pa — only the four modules we actually need
RUN cat > /etc/pulse/default.pa << 'EOF'
load-module module-native-protocol-unix
load-module module-null-sink sink_name=grok_speaker sink_properties=device.description="GrokSpeaker"
load-module module-null-sink sink_name=discord_mic_sink sink_properties=device.description="DiscordMicSink"
load-module module-virtual-source source_name=discord_mic master=discord_mic_sink.monitor source_properties=device.description="DiscordMic"
EOF

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
