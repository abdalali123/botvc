import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
import time
from playwright.async_api import async_playwright

# التحقق من وجود مكتبة المعالجة الصوتية
try:
    from discord.sinks import Sink as DiscordSinkBase
    HAS_SINKS = True
except ImportError:
    HAS_SINKS = False
    DiscordSinkBase = object

BOT_TOKEN = os.getenv("DISCORD_TOKEN")
MY_GUILD = discord.Object(id=1408448201555447968)

def log(step: str, msg: str, level: str = "INFO"):
    print(f"[{level}] [{step}] {msg}", flush=True)

# ─── نظام مراقبة الاستقبال (Discord -> Grok) ───
class DiscordToGrokSink(DiscordSinkBase):
    def __init__(self, ffmpeg_proc):
        if HAS_SINKS:
            super().__init__()
        self._proc = ffmpeg_proc
        self.packet_count = 0
        self.last_log = 0

    def write(self, data, user):
        # التحقق من أن عملية FFmpeg لا تزال تعمل
        if self._proc and self._proc.returncode is None:
            try:
                # ضخ البيانات الصوتية الخام إلى ميكروفون Grok عبر PulseAudio
                self._proc.stdin.write(data.data)
                
                self.packet_count += 1
                now = time.time()
                # Debug: إشعار كل 5 ثوانٍ عند استلام صوت
                if now - self.last_log > 5:
                    log("DEBUG_IN", f"Pumping audio from {user} to Grok Mic. Packets: {self.packet_count}")
                    self.packet_count = 0
                    self.last_log = now
            except Exception as e:
                log("DEBUG_IN", f"Input Pipe Error: {e}", "ERROR")

class AudioBridge:
    def __init__(self):
        self._in_proc = None  # Discord -> Grok
        self._sink = None

    async def _start_output(self, vc: discord.VoiceClient):
        """التقاط صوت Grok وإرساله لديسكورد (حل مشكلة Coroutine)"""
        log("DEBUG_OUT", "Starting Grok Output Capture via FFmpegPCMAudio...")
        
        # استخدام FFmpegPCMAudio يحل مشكلة الـ Coroutine لأنه يتعامل مع الـ Pipe داخلياً
        # -f pulse -i grok_speaker.monitor: يلتقط أي صوت يخرج من متصفح Grok
        ffmpeg_options = {
            'before_options': '-f pulse -i grok_speaker.monitor',
            'options': '-ac 2 -ar 48000'
        }

        try:
            source = discord.FFmpegPCMAudio("pipe:0", **ffmpeg_options)
            # رفع مستوى الصوت لضمان الوضوح
            transformed_source = discord.PCMVolumeTransformer(source, volume=1.5)
            
            vc.play(transformed_source, after=lambda e: log("DEBUG_OUT", f"Output stream ended: {e}" if e else "Success"))
            log("DEBUG_OUT", "Grok -> Discord bridge active ✓")
        except Exception as e:
            log("DEBUG_OUT", f"Failed to start output: {e}", "ERROR")

    async def _start_input(self, vc: discord.VoiceClient):
        """استقبال صوتك من ديسكورد وضخه لـ Grok"""
        if not HAS_SINKS:
            log("DEBUG_IN", "Discord sinks not available", "ERROR")
            return

        # إرسال الصوت المستلم إلى ميكروفون Grok الوهمي
        cmd = [
            "ffmpeg", "-loglevel", "quiet",
            "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", "pipe:0",
            "-f", "pulse", "discord_mic_sink",
        ]
        
        log("DEBUG_IN", "Starting Discord Input Bridge...")
        self._in_proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE
        )
        
        self._sink = DiscordToGrokSink(self._in_proc)
        vc.listen(self._sink)
        log("DEBUG_IN", "Discord -> Grok bridge active ✓")

    async def start(self, vc: discord.VoiceClient):
        await self._start_output(vc)
        await self._start_input(vc)

    async def stop(self, vc: discord.VoiceClient):
        if vc:
            vc.stop()
        if self._in_proc:
            self._in_proc.terminate()
        log("bridge", "Stopped all audio pipelines ✓")

# ─── إعداد البوت والمتصفح ───
class GrokBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.bridge = AudioBridge()

    async def setup_hook(self):
        # التأكد من أن البوت يستخدم مسار PulseAudio الصحيح
        os.environ["PULSE_SERVER"] = "unix:/tmp/pulse/native"
        
        log("setup_hook", "Launching Chromium with PulseAudio support...")
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-setuid-sandbox", "--use-fake-ui-for-media-stream"]
        )
        
        # إعطاء صلاحية الميكروفون تلقائياً
        self.context = await self.browser.new_context(permissions=["microphone"])
        
        if os.path.exists("cookies.json"):
            with open("cookies.json") as f:
                await self.context.add_cookies(json.load(f))

        self.page = await self.context.new_page()
        log("setup_hook", "Navigating to Grok Voice...")
        await self.page.goto("https://grok.com/voice")
        
        # تسجيل الأوامر
        self.tree.add_command(nega, guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)
        log("setup_hook", "Bot ready and commands synced ✓")

bot = GrokBot()

@app_commands.command(name="nega", description="Connect Discord audio to Grok")
async def nega(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    
    if not interaction.user.voice:
        return await interaction.followup.send("⚠️ Please join a voice channel first!")

    try:
        # الاتصال بقناة الصوت
        vc = await interaction.user.voice.channel.connect()
        # بدء عملية الربط المزدوج
        await bot.bridge.start(vc)
        await interaction.followup.send("🎙️ **Grok Bridge Active!**\n- I'm listening to you.\n- Grok's voice is streaming here.")
    except Exception as e:
        log("COMMAND", f"Error in /nega: {e}", "ERROR")
        await interaction.followup.send(f"❌ Failed to connect: {e}")

bot.run(BOT_TOKEN)
