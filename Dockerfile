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

# ── PulseAudio: dedicated pulse user (PA refuses to run as root without --system)
# auth-anonymous=1 on the socket lets the root bot process connect freely.
RUN groupadd -f pulse && \
    useradd -r -g pulse pulse 2>/dev/null || true && \
    mkdir -p /home/pulse /tmp/pulse && \
    chown -R pulse:pulse /home/pulse /tmp/pulse

# PA reads default.pa from $HOME/.config/pulse/ when not in system mode
RUN mkdir -p /home/pulse/.config/pulse && \
    cat > /home/pulse/.config/pulse/default.pa << 'EOF'
# Allow any local process (including root bot) to connect without cookie
load-module module-native-protocol-unix auth-anonymous=1 socket=/tmp/pulse/native
load-module module-null-sink sink_name=grok_speaker sink_properties=device.description="GrokSpeaker"
load-module module-null-sink sink_name=discord_mic_sink sink_properties=device.description="DiscordMicSink"
load-module module-virtual-source source_name=discord_mic master=discord_mic_sink.monitor source_properties=device.description="DiscordMic"
EOF
RUN chown -R pulse:pulse /home/pulse

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
