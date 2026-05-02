import discord
from discord import app_commands
from discord.ext import commands, voice_recv # إضافة voice_recv
import os
import asyncio
import json
import subprocess
from playwright.async_api import async_playwright

BOT_TOKEN = os.getenv("DISCORD_TOKEN")
MY_GUILD = discord.Object(id=1408448201555447968)

def log(step: str, msg: str, level: str = "INFO"):
    print(f"[{level}] [{step}] {msg}", flush=True)

class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.browser = None
        self.context = None
        self.page = None
        self.grok_ready = False

    async def setup_hook(self):
        log("setup_hook", "Starting Playwright with PulseAudio routing...")
        
        # توجيه المتصفح لاستخدام أجهزة الصوت الوهمية
        os.environ["PULSE_SINK"] = "grok_output"
        os.environ["PULSE_SOURCE"] = "user_voice_to_grok.monitor"

        try:
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--use-fake-ui-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required",
                ]
            )
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                permissions=["microphone"]
            )
            
            # تحميل الكوكيز
            if os.path.exists("cookies.json"):
                with open("cookies.json", "r") as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)

            self.page = await self.context.new_page()
            asyncio.create_task(self._load_grok())

        except Exception as e:
            log("setup_hook", f"FAILED: {e}", "ERROR")

        self.tree.add_command(nega, guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

    async def _load_grok(self):
        try:
            await self.page.goto("https://grok.com", wait_until="networkidle")
            self.grok_ready = True
            log("grok_load", "Grok page is READY ✓")
        except Exception as e:
            log("grok_load", f"Error: {e}", "ERROR")

bot = GrokBot()

# --- كلاس لاستقبال الصوت وتحويله إلى PulseAudio ---
class PulseAudioSink(voice_recv.AudioSink):
    def __init__(self):
        # فتح عملية ffmpeg لكتابة الصوت القادم من ديسكورد إلى ميكروفون Grok الوهمي
        self.process = subprocess.Popen(
            ['ffmpeg', '-f', 's16le', '-ar', '48000', '-ac', '2', '-i', '-', 
             '-f', 'pulse', 'user_voice_to_grok'],
            stdin=subprocess.PIPE
        )

    def write(self, user, data):
        if self.process.stdin:
            self.process.stdin.write(data.pcm)

    def cleanup(self):
        if self.process:
            self.process.terminate()

@app_commands.command(name="nega", description="Connect Grok voice to VC")
async def nega(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    if not interaction.user.voice:
        return await interaction.followup.send("⚠️ Join a VC first!")

    # 1. الاتصال بالقناة الصوتية
    channel = interaction.user.voice.channel
    vc = await channel.connect(cls=voice_recv.VoiceRecvClient)

    # 2. تشغيل وضع الصوت في Grok
    try:
        await bot.page.click('button[aria-label="Enter voice mode (Ctrl+⇧O)"]', timeout=5000)
        await asyncio.sleep(2)
        
        # 3. الجسر الصوتي الأول: من Grok إلى Discord (سماع Grok)
        grok_audio = discord.FFmpegPCMAudio(
            source="grok_output.monitor",
            before_options="-f pulse",
            options="-af volume=1.5"
        )
        vc.play(grok_audio)

        # 4. الجسر الصوتي الثاني: من المستخدمين إلى Grok (تحدث إلى Grok)
        vc.listen(PulseAudioSink())

        await interaction.followup.send("🎙️ **Grok متصل الآن!** يمكنك التحدث معه مباشرة.")

    except Exception as e:
        await interaction.followup.send(f"❌ فشل الاتصال الصوتي: `{e}`")

@bot.event
async def on_ready():
    log("on_ready", f"Logged in as {bot.user}")

bot.run(BOT_TOKEN)
