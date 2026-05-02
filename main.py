import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
import time
from playwright.async_api import async_playwright

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

class DiscordToGrokSink(DiscordSinkBase):
    def __init__(self, ffmpeg_proc):
        if HAS_SINKS: super().__init__()
        self._proc = ffmpeg_proc
        self.packet_count = 0
        self.last_log = 0

    def write(self, data, user):
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.stdin.write(data.data)
                self.packet_count += 1
                now = time.time()
                if now - self.last_log > 5:
                    log("DEBUG_IN", f"Audio Flowing: {self.packet_count} packets")
                    self.packet_count = 0
                    self.last_log = now
            except: pass

class AudioBridge:
    def __init__(self):
        self._in_proc = None

    async def _start_output(self, vc: discord.VoiceClient):
        """بث صوت Grok إلى ديسكورد باستخدام FFmpegPCMAudio المدمج"""
        log("DEBUG_OUT", "Initializing Output Stream...")
        
        # استخدام FFmpegPCMAudio يحل مشكلة الـ Coroutine نهائياً
        ffmpeg_options = {
            'before_options': '-f pulse -i grok_speaker.monitor',
            'options': '-ac 2 -ar 48000'
        }

        try:
            # pipe:0 هنا تشير إلى أن FFmpeg سيستخدم خيارات before_options للالتقاط
            source = discord.FFmpegPCMAudio("pipe:0", **ffmpeg_options)
            transformed = discord.PCMVolumeTransformer(source, volume=1.5)
            vc.play(transformed, after=lambda e: log("DEBUG_OUT", f"Stream ended: {e}" if e else "Finished"))
            log("DEBUG_OUT", "Grok -> Discord bridge active ✓")
        except Exception as e:
            log("DEBUG_OUT", f"Capture Error: {e}", "ERROR")

    async def _start_input(self, vc: discord.VoiceClient):
        """استقبال صوت ديسكورد وإرساله لـ Grok"""
        if not HAS_SINKS: return
        cmd = ["ffmpeg", "-loglevel", "quiet", "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", "pipe:0", "-f", "pulse", "discord_mic_sink"]
        self._in_proc = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE)
        vc.listen(DiscordToGrokSink(self._in_proc))
        log("DEBUG_IN", "Discord -> Grok bridge active ✓")

class GrokBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.bridge = AudioBridge()

    async def setup_hook(self):
        os.environ["PULSE_SERVER"] = "unix:/tmp/pulse/native"
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=True, args=["--no-sandbox", "--use-fake-ui-for-media-stream"])
        self.context = await self.browser.new_context(permissions=["microphone"])
        
        if os.path.exists("cookies.json"):
            with open("cookies.json") as f:
                await self.context.add_cookies(json.load(f))

        self.page = await self.context.new_page()
        await self.page.goto("https://grok.com/voice")
        
        self.tree.add_command(nega, guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)
        log("setup", "Bot Ready ✓")

bot = GrokBot()

@app_commands.command(name="nega", description="Bridge Audio")
async def nega(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    if not interaction.user.voice:
        return await interaction.followup.send("Join VC!")
    
    vc = await interaction.user.voice.channel.connect()
    await bot.bridge._start_output(vc)
    await bot.bridge._start_input(vc)
    await interaction.followup.send("🎙️ Bridge Connected.")

bot.run(BOT_TOKEN)
