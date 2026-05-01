FROM python:3.9-slim
    RUN apt-get update && apt-get install -y \
        git build-essential python3-dev libffi-dev libopus-dev \
        ffmpeg pulseaudio xvfb libnss3 ca-certificates \
        && rm -rf /var/lib/apt/lists/*
    WORKDIR /app
    COPY requirements.txt .
    RUN pip install --no-cache-dir -U pip setuptools wheel
    RUN pip install --no-cache-dir -r requirements.txt
    RUN playwright install chromium
    RUN playwright install-deps
    COPY . .
    CMD pulseaudio -D --exit-idle-time=-1 --system --disallow-exit; python main.py
    ```

### لماذا هذا الكود هو الأفضل لك؟
*   **Slash Command:** سيظهر لك بمجرد كتابة `/i` ويطلب منك إكمال النص تلقائياً.
*   **تجاوز خطأ Davey:** باستخدام نسخة الـ `git` من المكتبة وتحميل `libopus-dev` في الـ Dockerfile، قمنا بحل مشكلة التشفير الجديد.
*   **Playwright Stealth:** يتخفى المتصفح لكي لا يتم حظره من قبل نظام حماية X.com.

ارفع الكود الآن، وستجد أن "الظلال" أصبحت تحت أمرك في القناة الصوتية! 🌑
