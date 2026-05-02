FROM python:3.9-slim

# تثبيت الأدوات الأساسية
RUN apt-get update && apt-get install -y \
    git build-essential python3-dev libffi-dev libopus-dev \
    ffmpeg pulseaudio xvfb libnss3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# إعداد مستخدم للعمل لتجنب مشاكل System Mode في PulseAudio
RUN useradd -m -u 1000 botuser && \
    usermod -aG audio,video botuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps

COPY . .

# تأكد من ملكية الملفات للمستخدم الجديد
RUN chown -R botuser:botuser /app

# التبديل للمستخدم botuser
USER botuser

# أمر التشغيل المحدث: تشغيل PulseAudio كخدمة مستخدم عادية
CMD pulseaudio --start --exit-idle-time=-1 && \
    pacmd load-module module-null-sink sink_name=grok_output sink_properties=device.description="Grok_Output" && \
    pacmd load-module module-null-sink sink_name=user_voice_to_grok sink_properties=device.description="User_Voice_To_Grok" && \
    python main.py
