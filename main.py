import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
import time
import subprocess
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
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level:8}] [{step:15}] {msg}", flush=True)

def check_pulseaudio():
    """Verify PulseAudio is running and accessible"""
    try:
        result = subprocess.run(['pactl', 'info'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            log("PULSE", "PulseAudio daemon is running ✓")
            return True
        else:
            log("PULSE", f"pactl error: {result.stderr}", "ERROR")
            return False
    except Exception as e:
        log("PULSE", f"Cannot reach PulseAudio: {e}", "ERROR")
        return False

def check_audio_devices():
    """Verify null sinks and monitor devices exist"""
    try:
        result = subprocess.run(['pactl', 'list', 'sinks'], capture_output=True, text=True, timeout=5)
        sinks = result.stdout
        
        has_grok = "grok_speaker" in sinks
        has_discord = "discord_mic_sink" in sinks
        
        if has_grok:
            log("PULSE", "✓ grok_speaker sink found")
        else:
            log("PULSE", "✗ grok_speaker sink NOT found", "WARN")
            
        if has_discord:
            log("PULSE", "✓ discord_mic_sink found")
        else:
            log("PULSE", "✗ discord_mic_sink NOT found", "WARN")
        
        return has_grok and has_discord
    except Exception as e:
        log("PULSE", f"Cannot check sinks: {e}", "ERROR")
        return False

class DiscordToGrokSink(DiscordSinkBase):
    """Sink for capturing Discord voice and sending to Grok"""
    def __init__(self, ffmpeg_proc):
        if HAS_SINKS:
            super().__init__()
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
                    log("AUDIO_IN", f"Packets flowing: {self.packet_count}")
                    self.packet_count = 0
                    self.last_log = now
            except Exception as e:
                log("AUDIO_IN", f"Write failed: {e}", "WARN")

class AudioBridge:
    """Manages bidirectional audio flow between Discord and Grok"""
    def __init__(self):
        self._in_proc = None
        self._out_player = None

    async def _start_output(self, vc: discord.VoiceClient):
        """
        Stream audio from Grok speaker sink to Discord.
        This reads from the grok_speaker.monitor device.
        """
        log("AUDIO_OUT", "Starting Grok→Discord stream...")
        
        try:
            # Read from the PulseAudio monitor device of the null sink
            # The monitor device automatically captures everything sent to grok_speaker
            source = discord.FFmpegPCMAudio(
                "-f pulse -i grok_speaker.monitor -t 3600",
                before_options="",
                options="-ac 2 -ar 48000 -b:a 128k"
            )
            
            # Adjust volume and play
            transformed = discord.PCMVolumeTransformer(source, volume=1.5)
            vc.play(transformed, after=self._on_playback_end)
            
            log("AUDIO_OUT", "Grok→Discord bridge ACTIVE ✓")
            self._out_player = vc
            
        except Exception as e:
            log("AUDIO_OUT", f"FFmpeg capture failed: {e}", "ERROR")
            log("AUDIO_OUT", "Ensure PulseAudio null sinks are created", "ERROR")

    async def _start_input(self, vc: discord.VoiceClient):
        """
        Capture Discord voice and send to Grok via discord_mic_sink.
        This remaps Discord audio to the Grok input.
        """
        if not HAS_SINKS:
            log("AUDIO_IN", "discord-ext-voice-recv not available, skipping", "WARN")
            return
        
        log("AUDIO_IN", "Starting Discord→Grok stream...")
        
        try:
            # FFmpeg command: receive Discord audio (s16le format) and send to PulseAudio
            cmd = [
                "ffmpeg",
                "-loglevel", "error",
                "-f", "s16le",
                "-ar", "48000",
                "-ac", "2",
                "-i", "pipe:0",
                "-f", "pulse",
                "-t", "3600",  # 1-hour timeout
                "discord_mic_sink"
            ]
            
            self._in_proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Start listening to Discord voice
            vc.listen(DiscordToGrokSink(self._in_proc))
            log("AUDIO_IN", "Discord→Grok bridge ACTIVE ✓")
            
        except Exception as e:
            log("AUDIO_IN", f"Setup failed: {e}", "ERROR")

    def _on_playback_end(self, error):
        """Called when Discord playback finishes"""
        if error:
            log("AUDIO_OUT", f"Playback error: {error}", "ERROR")
        else:
            log("AUDIO_OUT", "Playback ended normally")

    async def stop(self, vc: discord.VoiceClient):
        """Stop all audio bridges"""
        if self._out_player:
            self._out_player.stop()
            log("AUDIO_OUT", "Stopped Grok→Discord")
        
        if self._in_proc:
            try:
                self._in_proc.terminate()
                await asyncio.wait_for(self._in_proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                self._in_proc.kill()
            log("AUDIO_IN", "Stopped Discord→Grok")

class GrokBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.bridge = AudioBridge()
        self.page = None
        self.context = None
        self.browser = None
        self.pw = None

    async def setup_hook(self):
        """Initialize bot, set up Playwright, configure PulseAudio"""
        log("SETUP", "Bot initializing...")
        
        # ============ PULSEAUDIO VERIFICATION ============
        if not check_pulseaudio():
            log("SETUP", "PulseAudio not ready, waiting 2 seconds...", "WARN")
            await asyncio.sleep(2)
            
            if not check_pulseaudio():
                log("SETUP", "PulseAudio still unavailable - audio bridges will fail", "ERROR")
        
        if not check_audio_devices():
            log("SETUP", "Audio devices not configured - falling back to Discord voice only", "WARN")
        
        # ============ PLAYWRIGHT SETUP ============
        try:
            log("SETUP", "Starting Playwright...")
            os.environ["PULSE_SERVER"] = "unix:/tmp/pulse/native"
            
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--use-fake-ui-for-media-stream"
                ]
            )
            
            self.context = await self.browser.new_context(
                permissions=["microphone"],
                ignore_https_errors=True
            )
            
            # ============ LOAD COOKIES ============
            cookies_file = os.path.join(os.path.dirname(__file__), "cookies.json")
            if os.path.exists(cookies_file):
                try:
                    with open(cookies_file) as f:
                        cookies = json.load(f)
                        await self.context.add_cookies(cookies)
                        log("SETUP", f"Loaded {len(cookies)} cookies ✓")
                except json.JSONDecodeError as e:
                    log("SETUP", f"Invalid cookies.json: {e}", "WARN")
                except Exception as e:
                    log("SETUP", f"Cookie load error: {e}", "WARN")
            else:
                log("SETUP", f"cookies.json not found at {cookies_file}", "WARN")
            
            # ============ NAVIGATE TO GROK ============
            log("SETUP", "Navigating to Grok...")
            self.page = await self.context.new_page()
            
            try:
                await self.page.goto("https://grok.com/voice", timeout=30000)
                log("SETUP", "Grok page loaded ✓")
            except Exception as e:
                log("SETUP", f"Grok navigation failed: {e}", "ERROR")
            
            # ============ REGISTER COMMAND ============
            self.tree.add_command(nega, guild=MY_GUILD)
            await self.tree.sync(guild=MY_GUILD)
            log("SETUP", "Commands synced ✓")
            
        except Exception as e:
            log("SETUP", f"Critical error: {e}", "ERROR")
            raise

    async def close(self):
        """Cleanup on shutdown"""
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()
        await super().close()

# ============ BOT INSTANCE & COMMAND ============
bot = GrokBot()

@app_commands.command(name="nega", description="Bridge Discord voice with Grok")
async def nega(interaction: discord.Interaction):
    """
    Slash command to connect bot to voice channel and start audio bridges.
    Usage: /nega
    """
    await interaction.response.defer(thinking=True)
    
    # Check if user is in voice
    if not interaction.user.voice:
        return await interaction.followup.send(
            "❌ Join a voice channel first!"
        )
    
    try:
        # Connect to user's voice channel
        channel = interaction.user.voice.channel
        log("COMMAND", f"Connecting to {channel.name}...")
        vc = await channel.connect()
        
        # Start audio bridges
        log("COMMAND", "Starting audio bridges...")
        await bot.bridge._start_output(vc)
        await bot.bridge._start_input(vc)
        
        await interaction.followup.send(
            "✅ **Audio Bridge Active**\n"
            "• Grok voice → Discord ✓\n"
            "• Discord voice → Grok ✓"
        )
        
        log("COMMAND", "Bridge connected successfully")
        
    except discord.errors.ClientException as e:
        log("COMMAND", f"Already connected or connection failed: {e}", "ERROR")
        await interaction.followup.send(f"❌ Connection error: {e}")
    except Exception as e:
        log("COMMAND", f"Unexpected error: {e}", "ERROR")
        await interaction.followup.send(f"❌ Error: {e}")

# ============ RUN BOT ============
if __name__ == "__main__":
    if not BOT_TOKEN:
        log("STARTUP", "DISCORD_TOKEN not set!", "ERROR")
        exit(1)
    
    try:
        bot.run(BOT_TOKEN)
    except KeyboardInterrupt:
        log("STARTUP", "Bot stopped by user")
    except Exception as e:
        log("STARTUP", f"Fatal error: {e}", "ERROR")
        raise
