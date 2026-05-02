import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
import time
from playwright.async_api import async_playwright

# ============ VOICE RECV (for Discord → Grok audio) ============
try:
    from discord.ext.voice_recv import VoiceRecvClient, AudioSink
    HAS_VOICE_RECV = True
except ImportError:
    HAS_VOICE_RECV = False
    VoiceRecvClient = None
    AudioSink = object

BOT_TOKEN = os.getenv("DISCORD_TOKEN")
MY_GUILD = discord.Object(id=1408448201555447968)

# Check at startup whether PulseAudio is reachable
def _pulse_available() -> bool:
    import subprocess
    try:
        result = subprocess.run(
            ["pactl", "info"],
            capture_output=True, timeout=3
        )
        return result.returncode == 0
    except Exception:
        return False

PULSE_AVAILABLE = _pulse_available()


def log(step: str, msg: str, level: str = "INFO"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level:8}] [{step:15}] {msg}", flush=True)


# ============ AUDIO SINK: Discord → Grok ============

class DiscordToGrokSink(AudioSink if HAS_VOICE_RECV else object):
    """
    Receives decoded PCM from Discord users and pipes it into PulseAudio
    (discord_mic_sink), so Grok's browser can hear it as a microphone input.
    """

    def __init__(self, pacat_proc):
        if HAS_VOICE_RECV:
            super().__init__()
        self._proc = pacat_proc
        self.packet_count = 0
        self.last_log = 0.0

    def wants_opus(self) -> bool:
        return False  # Request decoded PCM, not raw Opus

    def write(self, user, data):
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.stdin.write(data.pcm)
                self.packet_count += 1
                now = time.time()
                if now - self.last_log > 5:
                    log("AUDIO_IN", f"Discord→Grok packets flowing: {self.packet_count}")
                    self.packet_count = 0
                    self.last_log = now
            except Exception as e:
                log("AUDIO_IN", f"Write failed: {e}", "WARN")

    def cleanup(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass


# ============ AUDIO BRIDGE ============

class AudioBridge:
    """
    Bidirectional audio bridge between Discord and Grok (via PulseAudio + FFmpeg).

    Grok → Discord:
      Chromium (PULSE_SINK=grok_speaker) → grok_speaker PulseAudio sink
      → FFmpegPCMAudio reads grok_speaker.monitor → Discord VoiceClient plays it

    Discord → Grok:
      discord-ext-voice-recv captures voice → DiscordToGrokSink writes PCM
      → pacat pipes into discord_mic_sink → Chromium uses discord_mic as mic input
    """

    def __init__(self):
        self._in_sink = None
        self._in_proc = None

    async def _start_output(self, vc: discord.VoiceClient):
        """Stream Grok audio → Discord voice channel via FFmpeg + PulseAudio."""
        if not PULSE_AVAILABLE:
            log("AUDIO_OUT", "PulseAudio not available — Grok→Discord bridge skipped", "WARN")
            return
        try:
            source = discord.FFmpegPCMAudio(
                "grok_speaker.monitor",
                pipe=False,
                before_options="-f pulse -ac 2 -ar 48000",
                options="-ac 2 -ar 48000",
            )
            vc.play(
                discord.PCMVolumeTransformer(source, volume=1.0),
                after=self._on_playback_end,
            )
            log("AUDIO_OUT", "Grok→Discord stream started ✓")
        except Exception as e:
            log("AUDIO_OUT", f"Failed to start Grok→Discord bridge: {e}", "ERROR")

    async def _start_input(self, vc):
        """Capture Discord audio → pacat → discord_mic_sink → Grok microphone."""
        if not PULSE_AVAILABLE:
            log("AUDIO_IN", "PulseAudio not available — Discord→Grok bridge skipped", "WARN")
            return
        if not HAS_VOICE_RECV:
            log("AUDIO_IN", "discord-ext-voice-recv missing — Discord→Grok bridge skipped", "WARN")
            return
        try:
            # pacat writes raw PCM into the discord_mic_sink virtual device
            self._in_proc = await asyncio.create_subprocess_exec(
                "pacat", "--playback",
                "--device=discord_mic_sink",
                "--format=s16le",
                "--rate=48000",
                "--channels=2",
                stdin=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._in_sink = DiscordToGrokSink(self._in_proc)
            vc.listen(self._in_sink)
            log("AUDIO_IN", "Discord→Grok stream started ✓")
        except FileNotFoundError:
            log("AUDIO_IN", "pacat not found — is pulseaudio-utils installed?", "ERROR")
        except Exception as e:
            log("AUDIO_IN", f"Failed to start Discord→Grok bridge: {e}", "ERROR")

    def _on_playback_end(self, error):
        if error:
            log("AUDIO_OUT", f"Playback error: {error}", "ERROR")
        else:
            log("AUDIO_OUT", "Grok→Discord playback ended")

    async def stop(self, vc: discord.VoiceClient):
        """Tear down both audio bridges cleanly."""
        if vc.is_playing():
            vc.stop()
            log("AUDIO_OUT", "Stopped Grok→Discord")

        if self._in_sink:
            self._in_sink.cleanup()
            self._in_sink = None

        if self._in_proc:
            try:
                self._in_proc.terminate()
                await asyncio.wait_for(self._in_proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                self._in_proc.kill()
            self._in_proc = None
            log("AUDIO_IN", "Stopped Discord→Grok")


# ============ BOT ============

class GrokBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.bridge = AudioBridge()
        self.page = None
        self.context = None
        self.browser = None
        self.pw = None

    def _convert_browser_cookies(self, cookies):
        """Convert browser-extension cookie format → Playwright format."""
        playwright_cookies = []
        for cookie in cookies:
            pw_cookie = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie["domain"],
                "path": cookie.get("path", "/"),
            }
            if "expirationDate" in cookie:
                pw_cookie["expirationDate"] = int(cookie["expirationDate"])
            if "httpOnly" in cookie:
                pw_cookie["httpOnly"] = cookie["httpOnly"]
            if "secure" in cookie:
                pw_cookie["secure"] = cookie["secure"]

            same_site = cookie.get("sameSite", "unspecified")
            if not isinstance(same_site, str):
                same_site = "unspecified"
            same_site = same_site.lower()
            if same_site in ("unspecified", "none", "no_restriction"):
                pw_cookie["sameSite"] = "None"
            elif same_site == "lax":
                pw_cookie["sameSite"] = "Lax"
            elif same_site == "strict":
                pw_cookie["sameSite"] = "Strict"
            else:
                pw_cookie["sameSite"] = "None"

            playwright_cookies.append(pw_cookie)
        return playwright_cookies

    async def setup_hook(self):
        log("SETUP", "Bot initializing...")
        log("SETUP", f"PulseAudio available: {PULSE_AVAILABLE}")
        log("SETUP", f"VoiceRecv available:  {HAS_VOICE_RECV}")

        try:
            log("SETUP", "Starting Playwright...")
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--use-fake-ui-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            self.context = await self.browser.new_context(
                permissions=["microphone"],
                ignore_https_errors=True,
            )

            # ---- Load cookies ----
            cookies_file = os.path.join(os.path.dirname(__file__), "cookies.json")
            if os.path.exists(cookies_file):
                try:
                    with open(cookies_file) as f:
                        cookies = json.load(f)
                    if cookies and isinstance(cookies, list) and "hostOnly" in cookies[0]:
                        log("SETUP", "Converting cookies from browser export format...", "WARN")
                        cookies = self._convert_browser_cookies(cookies)
                    await self.context.add_cookies(cookies)
                    log("SETUP", f"Loaded {len(cookies)} cookies ✓")
                except json.JSONDecodeError as e:
                    log("SETUP", f"Invalid cookies.json: {e}", "WARN")
                except Exception as e:
                    log("SETUP", f"Cookie load error: {e}", "WARN")
            else:
                log("SETUP", "cookies.json not found — fresh login required", "WARN")

            # ---- Navigate to Grok ----
            log("SETUP", "Navigating to Grok...")
            self.page = await self.context.new_page()
            try:
                await self.page.goto("https://grok.com/voice", timeout=30000)
                log("SETUP", "Grok page loaded ✓")
            except Exception as e:
                log("SETUP", f"Grok navigation failed: {e}", "ERROR")

            # ---- Register commands ----
            self.tree.add_command(nega, guild=MY_GUILD)
            self.tree.add_command(leave, guild=MY_GUILD)
            await self.tree.sync(guild=MY_GUILD)
            log("SETUP", "Commands synced ✓")

        except Exception as e:
            log("SETUP", f"Critical setup error: {e}", "ERROR")
            raise

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()
        await super().close()


bot = GrokBot()


# ============ /nega COMMAND ============

@app_commands.command(name="nega", description="Bridge Discord voice with Grok")
async def nega(interaction: discord.Interaction):
    """
    Connect the bot to your voice channel and start the Grok ↔ Discord audio bridge.
    """
    # BUG FIX: defer() must be called within 3 seconds.
    # Wrap in try/except to handle expired or duplicate interactions gracefully.
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.NotFound:
        log("COMMAND", "Interaction token expired before defer() — possible duplicate instance", "WARN")
        return
    except Exception as e:
        log("COMMAND", f"defer() failed: {e}", "WARN")
        return

    if not interaction.user.voice:
        return await interaction.followup.send("❌ You need to join a voice channel first!")

    if interaction.guild.voice_client:
        return await interaction.followup.send(
            "⚠️ Already connected to a voice channel. Use `/leave` to disconnect first."
        )

    try:
        channel = interaction.user.voice.channel
        log("COMMAND", f"Connecting to {channel.name}...")

        # Use VoiceRecvClient so we can receive audio from Discord users
        if HAS_VOICE_RECV and VoiceRecvClient is not None:
            vc = await channel.connect(cls=VoiceRecvClient)
        else:
            vc = await channel.connect()

        log("COMMAND", "Starting audio bridges...")
        await bot.bridge._start_output(vc)
        await bot.bridge._start_input(vc)

        if PULSE_AVAILABLE:
            status = (
                "✅ **Audio Bridge Active**\n"
                "• Grok voice → Discord ✓\n"
                "• Discord voice → Grok ✓"
            )
        else:
            status = (
                "⚠️ **Connected** (PulseAudio unavailable — audio routing disabled)\n"
                "• Voice channel joined ✓\n"
                "• Run startup.sh to enable audio bridges"
            )

        await interaction.followup.send(status)
        log("COMMAND", "Bridge connected successfully")

    except discord.errors.ClientException as e:
        log("COMMAND", f"Already connected or connection failed: {e}", "ERROR")
        await interaction.followup.send(f"❌ Connection error: {e}")
    except Exception as e:
        log("COMMAND", f"Unexpected error: {e}", "ERROR")
        await interaction.followup.send(f"❌ Error: {e}")


# ============ /leave COMMAND ============

@app_commands.command(name="leave", description="Disconnect bot from voice and stop audio bridges")
async def leave(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.NotFound:
        return

    vc = interaction.guild.voice_client
    if not vc:
        return await interaction.followup.send("❌ Not connected to any voice channel.")

    try:
        await bot.bridge.stop(vc)
        await vc.disconnect()
        await interaction.followup.send("👋 Disconnected and audio bridges stopped.")
        log("COMMAND", "Disconnected from voice channel")
    except Exception as e:
        log("COMMAND", f"Leave error: {e}", "ERROR")
        await interaction.followup.send(f"❌ Error while disconnecting: {e}")


# ============ RUN ============

if __name__ == "__main__":
    if not BOT_TOKEN:
        log("STARTUP", "DISCORD_TOKEN environment variable not set!", "ERROR")
        exit(1)
    try:
        bot.run(BOT_TOKEN)
    except KeyboardInterrupt:
        log("STARTUP", "Bot stopped by user")
    except Exception as e:
        log("STARTUP", f"Fatal error: {e}", "ERROR")
        raise
