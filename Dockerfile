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

# ── PulseAudio: create socket dir + minimal system config ────────────────────
RUN mkdir -p /var/run/pulse /etc/pulse && chmod 755 /var/run/pulse

# Load only what we need — avoids the "Daemon startup failed" crash
# that happens when the default system.pa references missing modules.
RUN cat > /etc/pulse/system.pa << 'EOF'
#!/usr/bin/pulseaudio -nF
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
