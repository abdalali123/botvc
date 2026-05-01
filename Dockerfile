FROM python:3.9-slim

# تثبيت الأدوات اللازمة لبناء نظام التشفير والمتصفح والصوت
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    python3-dev \
    libffi-dev \
    libopus-dev \
    ffmpeg \
    pulseaudio \
    xvfb \
    libnss3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تحديث أدوات التثبيت وتثبيت المكتبات
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# تثبيت محرك Playwright والاعتمادات الخاصة به
RUN playwright install chromium
RUN playwright install-deps

COPY . .

# تشغيل نظام الصوت ثم البوت
CMD pulseaudio -D --exit-idle-time=-1 --system --disallow-exit; python main.py
