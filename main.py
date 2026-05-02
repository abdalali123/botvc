import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
import time
from playwright.async_api import async_playwright

# التحقق من وجود مكتبة المعالجة الصوتية (Sinks)
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

# ─── نظام مراقبة الصوت القادم من ديسكورد ───
class DiscordToGrokSink(DiscordSinkBase):
    def __init__(self, ffmpeg_proc):
        if HAS_SINKS:
            super().__init__()
        self._proc = ffmpeg_proc
        self.packet_count = 0
        self.last_log = 0

    def write(self, data, user):
        if self._proc and self._proc.returncode is None:
            try:
                # ضخ صوت المستخدم إلى ميكروفون Grok
                self._proc.stdin.write(data.data)
                self.packet_count += 1
                now = time.time()
                if now - self.last_log > 5:
                    log("DEBUG_IN", f"Audio flowing from {user}. Packets: {self.packet_count}")
                    self.packet_count = 0
                    self.last_log = now
            except Exception as e:
                log("DEBUG_IN", f"Pipe Error: {e}", "ERROR")

class AudioBridge:
    def __init__(self):
        self._in_proc = None
        self._sink = None

    async def _start_output(self, vc: discord.VoiceClient):
        """بث صوت Grok إلى ديسكورد (تم الإصلاح لمنع خطأ Coroutine)"""
        log("DEBUG_OUT", "Connecting Grok Output to Discord...")
        
        # استخدام FFmpegPCMAudio المدمج في ديسكورد لتجنب مشاكل الـ Async
        ffmpeg_options = {
            'before_options': '-f pulse -i grok_speaker.monitor',
            'options': '-ac 2 -ar 48000'
        }

        try:
            source = discord.FFmpegPCMAudio("pipe:0", **ffmpeg_options)
            # رفع مستوى الصوت بنسبة 1.5
            transformed = discord.PCMVolumeTransformer(source, volume=1.5)
            vc.play(transformed, after=lambda e: log("DEBUG_OUT", f"Stream ended: {e}" if e else "Finished"))
            log("DEBUG_OUT", "Grok -> Discord bridge active ✓")
        except Exception as e:
            log("DEBUG_OUT", f"Failed: {e}", "ERROR")

    async def _start_input(self, vc: discord.VoiceClient):
        """استقبال صوت ديسكورد وإرساله لـ Grok"""
        if not HAS_SINKS: return

        cmd = [
            "ffmpeg", "-loglevel", "quiet",
            "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", "pipe:0",
            "-f", "pulse", "discord_mic_sink",
        ]
        
        log("DEBUG_IN", "Starting Discord -> Grok Pipeline...")
        self._in_proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE
        )
        
        self._sink = DiscordToGrokSink(self._in_proc)
        vc.listen(self._sink)
        log("DEBUG_IN", "Discord -> Grok bridge active ✓")

    async def stop(self, vc: discord.VoiceClient):
        if vc: vc.stop()
        if self._in_proc: self._in_proc.terminate()
        log("bridge", "Bridge stopped ✓")

# ─── البوت والمتصفح ───
class GrokBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.bridge = AudioBridge()

    async def setup_hook(self):
        os.environ["PULSE_SERVER"] = "unix:/tmp/pulse/native"
        
        log("setup", "Launching Browser...")
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
        log("setup", "Syncing commands and ready ✓")

bot = GrokBot()

@app_commands.command(name="nega", description="Bridge Voice to Grok")
async def nega(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    if not interaction.user.voice:
        return await interaction.followup.send("Join a VC first!")

    vc = await interaction.user.voice.channel.connect()
    await bot.bridge._start_output(vc)
    await bot.bridge._start_input(vc)
    await interaction.followup.send("🎙️ **Bridge Active.** Sound is now flowing between Discord and Grok.")

bot.run(BOT_TOKEN)
