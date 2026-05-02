import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
import subprocess
import time
from playwright.async_api import async_playwright

# التحقق من وجود مكتبة السوفتوير لمعالجة الصوت
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

# ─── نظام الـ Debug للاستقبال (Discord -> Grok) ───
class DiscordToGrokSink(DiscordSinkBase):
    def __init__(self, ffmpeg_stdin):
        if HAS_SINKS:
            super().__init__()
        self._stdin = ffmpeg_stdin
        self.packet_count = 0
        self.last_log = 0

    def write(self, data, user):
        if self._stdin and not self._stdin.is_closing():
            try:
                self._stdin.write(data.data)
                self.packet_count += 1
                
                # Debug: طباعة حالة الاستقبال كل 5 ثوانٍ
                now = time.time()
                if now - self.last_log > 5:
                    log("DEBUG_IN", f"Receiving audio from {user}. Packets since last log: {self.packet_count}")
                    self.packet_count = 0
                    self.last_log = now
            except Exception as e:
                log("DEBUG_IN", f"Pipe Error: {e}", "ERROR")

class AudioBridge:
    def __init__(self):
        self._out_proc = None # Grok -> Discord
        self._in_proc = None  # Discord -> Grok
        self._sink = None

    async def _start_output(self, vc: discord.VoiceClient):
        """التقاط صوت Grok وإرساله لديسكورد"""
        cmd = [
            "ffmpeg", "-loglevel", "info", 
            "-f", "pulse", "-i", "grok_speaker.monitor",
            "-ac", "2", "-ar", "48000",
            "-f", "s16le", "pipe:1",
        ]
        log("DEBUG_OUT", "Starting Grok Output Capture...")
        self._out_proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        
        # قراءة الـ stderr لمراقبة أخطاء ffmpeg في الخلفية
        async def track_out_errors():
            while True:
                line = await self._out_proc.stderr.readline()
                if not line: break
                if b"error" in line.lower():
                    log("DEBUG_OUT_FFMPEG", line.decode().strip(), "WARN")

        asyncio.create_task(track_out_errors())
        
        source = discord.PCMAudio(self._out_proc.stdout)
        vc.play(discord.PCMVolumeTransformer(source, volume=1.5))
        log("DEBUG_OUT", "Grok -> Discord bridge active ✓")

    async def _start_input(self, vc: discord.VoiceClient):
        """استقبال صوت ديسكورد وضخه لميكروفون Grok"""
        if not HAS_SINKS: return

        cmd = [
            "ffmpeg", "-loglevel", "info",
            "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", "pipe:0",
            "-f", "pulse", "discord_mic_sink",
        ]
        log("DEBUG_IN", "Starting Discord Input Bridge...")
        self._in_proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        self._sink = DiscordToGrokSink(self._in_proc.stdin)
        vc.listen(self._sink)
        log("DEBUG_IN", "Discord -> Grok bridge active ✓")

    async def start(self, vc: discord.VoiceClient):
        await self._start_output(vc)
        await self._start_input(vc)

    async def stop(self, vc: discord.VoiceClient):
        if vc: vc.stop()
        for p in [self._out_proc, self._in_proc]:
            if p: p.terminate()
        log("bridge", "Stopped all audio pipelines ✓")

# ─── Bot & Browser Setup ───
class GrokBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.bridge = AudioBridge()
        self.grok_ready = False

    async def setup_hook(self):
        # توحيد المسار داخلياً للبوت والمتصفح
        os.environ["PULSE_SERVER"] = "unix:/tmp/pulse/native"
        
        log("setup_hook", "Launching Chromium...")
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=True, args=["--no-sandbox", "--use-fake-ui-for-media-stream"])
        self.context = await self.browser.new_context(permissions=["microphone"])
        
        # تحميل الكوكيز (تأكد من وجود الملف)
        if os.path.exists("cookies.json"):
            with open("cookies.json") as f:
                await self.context.add_cookies(json.load(f))

        self.page = await self.context.new_page()
        await self.page.goto("https://grok.com/voice")
        self.grok_ready = True
        log("setup_hook", "Grok Voice Page Loaded ✓")

        self.tree.add_command(nega, guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

bot = GrokBot()

@app_commands.command(name="nega", description="Bridge audio between Discord and Grok")
async def nega(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    if not interaction.user.voice:
        return await interaction.followup.send("Join a VC!")

    vc = await interaction.user.voice.channel.connect()
    await bot.bridge.start(vc)
    await interaction.followup.send("🎙️ Audio Bridge Active. Watch Logs for DEBUG_IN/OUT.")

bot.run(BOT_TOKEN)
