FROM python:3.9-slim

# ============ INSTALL SYSTEM DEPENDENCIES ============
RUN apt-get update && apt-get install -y \
    git build-essential libffi-dev \
    libopus-dev \
    libnss3 ca-certificates libxss1 libatk-bridge2.0-0 \
    libglib2.0-0 \
    curl wget \
    && rm -rf /var/lib/apt/lists/*

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

# Make startup script executable
RUN chmod +x startup.sh

# ============ ENVIRONMENT CONFIGURATION ============
ENV HOME=/root
ENV PYTHONUNBUFFERED=1

# ============ RUN ============
CMD ["./startup.sh"]
