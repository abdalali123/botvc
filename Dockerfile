FROM python:3.9-slim

# تثبيت متطلبات النظام الضرورية للمتصفح والصوت
RUN apt-get update && apt-get install -y \
    pulseaudio \
    xvfb \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تثبيت المكتبات والمتصفح
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps

COPY . .

# تشغيل نظام الصوت الوهمي ثم البوت
CMD pulseaudio -D --exit-idle-time=-1 --system --disallow-exit; \
    python main.py
