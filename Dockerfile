FROM python:3.9-slim

# ============ INSTALL SYSTEM DEPENDENCIES ============
RUN apt-get update && apt-get install -y \
    git build-essential libffi-dev \
    libopus-dev ffmpeg pulseaudio pulseaudio-utils \
    libnss3 ca-certificates libxss1 libatk-bridge2.0-0 \
    libglib2.0-0 \
    curl wget \
    && rm -rf /var/lib/apt/lists/*

# ============ SETUP PULSE USER ============
# Create pulse user if it doesn't exist (for non-root PulseAudio operations)
RUN if ! id pulse > /dev/null 2>&1; then \
    useradd -m -r -d /home/pulse pulse; \
fi

# Ensure directories exist with proper permissions
RUN mkdir -p /tmp/pulse /home/pulse && \
    chown -R pulse:pulse /tmp/pulse /home/pulse

# ============ PYTHON DEPENDENCIES ============
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and Chromium
RUN playwright install chromium
RUN playwright install-deps

# ============ COPY APPLICATION FILES ============
COPY main.py .
COPY startup.sh .
COPY cookies.json . 2>/dev/null || true

# Make startup script executable
RUN chmod +x startup.sh

# ============ ENVIRONMENT CONFIGURATION ============
ENV PULSE_SERVER=unix:/tmp/pulse/native
ENV HOME=/root
ENV PYTHONUNBUFFERED=1

# ============ HEALTH CHECK ============
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD pactl info > /dev/null 2>&1 || exit 1

# ============ RUN ============
CMD ["./startup.sh"]
