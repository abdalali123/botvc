import discord
from discord import app_commands
from discord.ext import commands, voice_recv
import os
import asyncio
import json
import subprocess
from playwright.async_api import async_playwright

# --- الإعدادات الأساسية ---
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
# تأكد من أن الـ ID هو الخاص بسيرفرك البرمجي
MY_GUILD = discord.Object(id=1408448201555447968)

def log(step: str, msg: str, level: str = "INFO"):
    print(f"[{level}] [{step}] {msg}", flush=True)

# --- كلاس البوت ---
class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.browser = None
        self.context = None
        self.page = None
        self.grok_ready = False

    async def setup_hook(self):
        log("setup_hook", "Initializing PulseAudio environment variables...")
        
        # ربط المتصفح بأجهزة الصوت الوهمية التي تم إنشاؤها في Dockerfile
        os.environ["PULSE_SINK"] = "grok_output"
        os.environ["PULSE_SOURCE"] = "user_voice_to_grok.monitor"

        try:
            log("setup_hook", "Launching Browser...")
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--use-fake-ui-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required",
                ]
            )
            
            # إنشاء سياق المتصفح مع منح إذن الميكروفون
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                permissions=["microphone"]
            )
            
            # منح الإذن الصريح لرابط Grok لتجنب فشل الاتصال
            await self.context.grant_permissions(["microphone"], origin="https://grok.com")

            # تحميل الكوكيز إذا كانت موجودة
            if os.path.exists("cookies.json"):
                with open("cookies.json", "r") as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)
                log("setup_hook", "Cookies loaded ✓")

            self.page = await self.context.new_page()
            asyncio.create_task(self._load_grok())

        except Exception as e:
            log("setup_hook", f"Browser Setup FAILED: {e}", "ERROR")

        # مزامنة الأوامر
        self.tree.add_command(nega, guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)
        log("setup_hook", "Commands synced ✓")

    async def _load_grok(self):
        log("grok_load", "Navigating to Grok...")
        try:
            await self.page.goto("https://grok.com", wait_until="networkidle", timeout=60000)
            self.grok_ready = True
            log("grok_load", "Grok is READY ✓")
        except Exception as e:
            log("grok_load", f"Navigation failed: {e}", "ERROR")

bot = GrokBot()

# --- جسر إرسال صوت المستخدمين من ديسكورد إلى ميكروفون Grok ---
class PulseAudioSink(voice_recv.AudioSink):
    def __init__(self):
        # استخدام FFmpeg لضخ بيانات PCM القادمة من ديسكورد إلى جهاز PulseAudio الوهمي
        self.process = subprocess.Popen(
            ['ffmpeg', '-f', 's16le', '-ar', '48000', '-ac', '2', '-i', '-', 
             '-f', 'pulse', 'user_voice_to_grok'],
            stdin=subprocess.PIPE
        )

    def write(self, user, data):
        if self.process.stdin:
            try:
                self.process.stdin.write(data.pcm)
            except Exception:
                pass

    def cleanup(self):
        if self.process:
            self.process.terminate()
            log("PulseAudioSink", "FFmpeg process cleaned up.")

# --- الأمر الأساسي /nega ---
@app_commands.command(name="nega", description="Connect the shadow voice of Grok to your channel")
async def nega(interaction: discord.Interaction):
    log("nega", f"Called by {interaction.user}")
    await interaction.response.defer(thinking=True)

    # 1. التحقق من وجود المستخدم في قناة صوتية
    if not interaction.user.voice:
        return await interaction.followup.send("⚠️ You must be in a voice channel!")

    # 2. الاتصال بالقناة الصوتية باستخدام VoiceRecvClient
    try:
        channel = interaction.user.voice.channel
        vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
        log("nega", "Connected to Discord Voice Channel ✓")
    except Exception as e:
        return await interaction.followup.send(f"❌ Could not connect to VC: {e}")

    # 3. محاولة تشغيل وضع الصوت في Grok
    if not bot.grok_ready:
        return await interaction.followup.send("🌑 Grok is not ready yet. Please wait.")

    try:
        # البحث عن زر وضع الصوت والضغط عليه
        # ملاحظة: استخدمنا Selector مرن بناءً على الفحص السابق
        voice_selector = 'button[aria-label*="voice mode"]'
        await bot.page.wait_for_selector(voice_selector, timeout=10000)
        await bot.page.click(voice_selector)
        log("nega", "Clicked Grok voice mode button ✓")
        
        await asyncio.sleep(3) # انتظار استقرار الاتصال

        # 4. الجسر الصوتي الأول: إرسال صوت Grok إلى ديسكورد
        # نستخدم monitor لسماع مخرجات المتصفح
        grok_to_discord = discord.FFmpegPCMAudio(
            source="grok_output.monitor",
            before_options="-f pulse",
            options="-af volume=1.5"
        )
        if not vc.is_playing():
            vc.play(grok_to_discord)
            log("nega", "Routing Grok -> Discord started ✓")

        # 5. الجسر الصوتي الثاني: استقبال صوت المستخدمين وإرساله لـ Grok
        vc.listen(PulseAudioSink())
        log("nega", "Routing Discord -> Grok started ✓")

        await interaction.followup.send("🎙️ **The shadows have arrived.** Grok is now listening and speaking.")

    except Exception as e:
        log("nega", f"Grok Bridge Error: {e}", "ERROR")
        await interaction.followup.send(f"❌ Failed to bridge Grok: `{e}`")

@bot.event
async def on_ready():
    log("on_ready", f"Logged in as {bot.user} (ID: {bot.user.id})")

# تشغيل البوت
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable not set!")
    else:
        bot.run(BOT_TOKEN)
