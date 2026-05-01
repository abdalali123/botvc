FROM python:3.9-slim

# تثبيت الأساسيات فقط: الصوت، التشفير، والمتصفح
RUN apt-get update && apt-get install -y \
    git build-essential libffi-dev libopus-dev ffmpeg \
    pulseaudio xvfb libnss3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تحميل المكتبات: نستخدم git هنا لتحميل نسخة ديسكورد التي تدعم DAVE
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps

COPY . .

# تشغيل الصوت والبوت
CMD pulseaudio -D --exit-idle-time=-1 --system --disallow-exit; \
    python main.py
