import discord
from discord import app_commands
from discord.ext import commands, voice_recv
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
        log("setup_hook", "Initializing optimized environment for Railway...")
        
        # ربط PulseAudio بالمتصفح
        os.environ["PULSE_SINK"] = "grok_output"
        os.environ["PULSE_SOURCE"] = "user_voice_to_grok.monitor"

        try:
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--use-fake-ui-for-media-stream", # قبول الميكروفون تلقائياً
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-webrtc-hw-encoding",
                    "--disable-webrtc-hw-decoding",
                    "--force-webrtc-ip-handling-policy=default_public_interface_only"
                ]
            )
            self.context = await self.browser.new_page()
            
            # منح الإذن الصريح للميكروفون لتجاوز خطأ FAILED
            await self.context.context.grant_permissions(["microphone"], origin="https://grok.com")

            if os.path.exists("cookies.json"):
                with open("cookies.json", "r") as f:
                    await self.context.context.add_cookies(json.load(f))

            self.page = self.context
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

# --- جسر إرسال صوت ديسكورد إلى ميكروفون Grok ---
class PulseAudioSink(voice_recv.AudioSink):
    def __init__(self):
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

@app_commands.command(name="nega", description="Call Grok to your voice channel")
async def nega(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    if not interaction.user.voice:
        return await interaction.followup.send("⚠️ Join a voice channel first!")

    # 1. الاتصال الصوتي (استخدام VoiceRecvClient لاستقبال الصوت)
    channel = interaction.user.voice.channel
    vc = await channel.connect(cls=voice_recv.VoiceRecvClient)

    try:
        # 2. تفعيل وضع الصوت في Grok
        # البحث عن الزر بناءً على الـ aria-label الذي ظهر في الفحص السابق
        voice_btn = self.page.locator('button[aria-label*="voice mode"]')
        await voice_btn.click()
        await asyncio.sleep(3)

        # 3. الجسر الصوتي: سماع Grok (Grok Output -> Discord)
        grok_to_discord = discord.FFmpegPCMAudio(
            source="grok_output.monitor",
            before_options="-f pulse",
            options="-af volume=1.5"
        )
        if not vc.is_playing():
            vc.play(grok_to_discord)

        # 4. الجسر الصوتي: التحدث إلى Grok (Discord -> Grok Mic)
        vc.listen(PulseAudioSink())

        await interaction.followup.send("✅ **تم الاتصال!** Grok يسمعك الآن في القناة الصوتية.")

    except Exception as e:
        log("nega", f"Interaction error: {e}", "ERROR")
        await interaction.followup.send(f"❌ خطأ في الاتصال بـ Grok: `{e}`")

@bot.event
async def on_ready():
    log("on_ready", f"Bot online as {bot.user}")

bot.run(BOT_TOKEN)
