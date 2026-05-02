import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
import subprocess
from playwright.async_api import async_playwright

# discord.sinks is not re-exported from the top-level discord package in all builds
try:
    from discord.sinks import Sink as DiscordSinkBase
    HAS_SINKS = True
except ImportError:
    HAS_SINKS = False
    DiscordSinkBase = object  # dummy base so the class definition doesn't crash

BOT_TOKEN = os.getenv("DISCORD_TOKEN")
MY_GUILD = discord.Object(id=1408448201555447968)

# ─── helpers ──────────────────────────────────────────────────────────────────
def log(step: str, msg: str, level: str = "INFO"):
    print(f"[{level}] [{step}] {msg}", flush=True)

async def screenshot(page, name: str):
    path = f"/tmp/debug_{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        log("screenshot", f"Saved → {path}")
        return path
    except Exception as e:
        log("screenshot", f"Failed: {e}", "WARN")
        return None


# ─── Audio bridge ─────────────────────────────────────────────────────────────
class DiscordToGrokSink(DiscordSinkBase):
    """Receives audio from Discord VC and writes raw PCM to ffmpeg stdin."""

    def __init__(self, ffmpeg_stdin):
        if HAS_SINKS:
            super().__init__()
        self._stdin = ffmpeg_stdin

    def write(self, data, user):
        # data.data is raw PCM bytes (48 kHz, 16-bit, 2ch)
        if self._stdin and not self._stdin.is_closing():
            try:
                self._stdin.write(data.data)
            except Exception:
                pass

    def cleanup(self):
        pass


class AudioBridge:
    """
    Two pipelines:
      1. grok_speaker.monitor  →  ffmpeg  →  Discord PCM output
      2. Discord VC audio      →  ffmpeg  →  discord_mic_sink  →  Chromium mic
    """

    def __init__(self):
        self._out_proc = None   # grok → discord
        self._in_proc  = None   # discord → grok
        self._sink     = None

    # ── Grok → Discord ────────────────────────────────────────────────────────
    async def _start_output(self, vc: discord.VoiceClient):
        """Capture Grok's speaker output from PulseAudio and play into Discord."""
        cmd = [
            "ffmpeg", "-loglevel", "quiet",
            "-f", "pulse", "-i", "grok_speaker.monitor",
            "-ac", "2", "-ar", "48000",
            "-f", "s16le", "pipe:1",
        ]
        log("bridge", f"Starting output pipeline: {' '.join(cmd)}")
        self._out_proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        source = discord.PCMAudio(self._out_proc.stdout)
        vc.play(
            discord.PCMVolumeTransformer(source, volume=1.0),
            after=lambda e: log("bridge", f"Output pipeline ended: {e}"),
        )
        log("bridge", "Output pipeline started ✓")

    # ── Discord → Grok ────────────────────────────────────────────────────────
    async def _start_input(self, vc: discord.VoiceClient):
        """Receive Discord audio and pipe it into the PulseAudio virtual mic."""
        if not HAS_SINKS:
            log("bridge", "discord.sinks not available — Discord→Grok direction disabled", "WARN")
            return

        cmd = [
            "ffmpeg", "-loglevel", "quiet",
            "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", "pipe:0",
            "-f", "pulse", "discord_mic_sink",
        ]
        log("bridge", f"Starting input pipeline: {' '.join(cmd)}")
        self._in_proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._sink = DiscordToGrokSink(self._in_proc.stdin)
        vc.listen(self._sink)
        log("bridge", "Input pipeline started ✓")

    async def start(self, vc: discord.VoiceClient):
        await self._start_output(vc)
        await self._start_input(vc)

    async def stop(self, vc: discord.VoiceClient):
        vc.stop()
        try:
            vc.stop_listening()
        except Exception:
            pass
        for proc in (self._out_proc, self._in_proc):
            if proc:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except Exception:
                    pass
        self._out_proc = self._in_proc = self._sink = None
        log("bridge", "Audio bridge stopped ✓")


# ─── bot class ────────────────────────────────────────────────────────────────
class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.browser  = None
        self.context  = None
        self.page     = None
        self.grok_ready = False
        self.bridge   = AudioBridge()

    async def setup_hook(self):
        log("setup_hook", "Initializing PulseAudio environment variables...")
        # Ensure the PA system socket is visible to this process and to Chromium
        os.environ.setdefault("PULSE_RUNTIME_PATH", "/tmp/pulse")
        os.environ.setdefault("PULSE_SERVER", "unix:/tmp/pulse/native")

        log("setup_hook", "Launching Browser...")
        try:
            self.pw = await async_playwright().start()

            self.browser = await self.pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--window-size=1280,800",
                    # ✅ Keep: bypasses the browser permission UI popup
                    "--use-fake-ui-for-media-stream",
                    # ❌ REMOVED --use-fake-device-for-media-stream
                    #    That flag replaces real PulseAudio with a test tone,
                    #    breaking the audio bridge entirely.
                ],
            )
            log("setup_hook", "Browser launched ✓")

            self.context = await self.browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                timezone_id="America/New_York",
                permissions=["microphone", "camera"],
            )

            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver',  { get: () => undefined });
                Object.defineProperty(navigator, 'plugins',    { get: () => [1, 2, 3] });
                Object.defineProperty(navigator, 'languages',  { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)

            if os.path.exists("cookies.json"):
                with open("cookies.json") as f:
                    raw = json.load(f)
                MAP = {
                    "unspecified": "None", "no_restriction": "None",
                    "lax": "Lax", "strict": "Strict", "none": "None",
                }
                STRIP = {"hostOnly", "session", "storeId", "id"}
                cookies = []
                for c in raw:
                    fixed = {k: v for k, v in c.items() if k not in STRIP}
                    fixed["sameSite"] = MAP.get(str(fixed.get("sameSite", "None")).lower(), "None")
                    cookies.append(fixed)
                await self.context.add_cookies(cookies)
                log("setup_hook", f"Loaded {len(cookies)} cookies ✓")
            else:
                log("setup_hook", "No cookies.json — may hit login wall", "WARN")

            self.page = await self.context.new_page()
            asyncio.create_task(self._load_grok())

        except Exception as e:
            log("setup_hook", f"Browser setup FAILED: {e}", "ERROR")

        self.tree.clear_commands(guild=None)
        await self.tree.sync()
        self.tree.add_command(nega, guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)
        log("setup_hook", "Commands synced ✓")

    async def _load_grok(self):
        log("grok_load", "Navigating to https://grok.com …")
        try:
            resp = await self.page.goto(
                "https://grok.com", wait_until="domcontentloaded", timeout=30_000
            )
            log("grok_load", f"HTTP {resp.status}")
            await asyncio.sleep(5)

            for attempt in range(3):
                url = self.page.url
                log("grok_load", f"[attempt {attempt+1}] URL: {url}")

                err_count = await self.page.locator("text=Something went wrong").count()
                if err_count:
                    log("grok_load", "Error page — clicking Try again …", "WARN")
                    try:
                        await self.page.click("text=Try again", timeout=5000)
                        await asyncio.sleep(5)
                    except Exception:
                        pass
                    continue

                if "login" in url or "signin" in url:
                    log("grok_load", "Login redirect — cookies stale!", "WARN")
                    await screenshot(self.page, "01_login")
                    self.grok_ready = False
                    return
                break

            await screenshot(self.page, "01_after_load")
            title = await self.page.title()
            log("grok_load", f"Title: '{title}'")

            if "login" in self.page.url or "signin" in self.page.url:
                log("grok_load", "Still on login — aborting", "ERROR")
                self.grok_ready = False
                return

            self.grok_ready = True
            log("grok_load", "Grok page READY ✓")

        except Exception as e:
            log("grok_load", f"Navigation error: {e}", "ERROR")
            self.grok_ready = False


bot = GrokBot()


# ─── /nega command ────────────────────────────────────────────────────────────
@app_commands.command(name="nega", description="Call the shadows to join your voice channel")
async def nega(interaction: discord.Interaction):
    log("nega", f"Called by {interaction.user}")
    await interaction.response.defer(thinking=True)

    # ── 1. Voice check ────────────────────────────────────────────────────────
    if not interaction.user.voice:
        await interaction.followup.send("⚠️ Join a voice channel first!")
        return

    # ── 2. Join VC ────────────────────────────────────────────────────────────
    channel = interaction.user.voice.channel
    vc = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    try:
        if not vc:
            vc = await channel.connect()
            log("nega", f"Joined '{channel.name}' ✓")
        else:
            log("nega", "Already connected ✓")
    except Exception as e:
        await interaction.followup.send(f"❌ Could not join VC: `{e}`")
        return

    # ── 3. Grok readiness ─────────────────────────────────────────────────────
    if not bot.grok_ready or bot.page is None:
        await interaction.followup.send("🌑 Joined VC — but Grok page isn't ready yet.")
        return

    # ── 4. Navigate to Voice page directly ───────────────────────────────────
    log("nega", "Navigating to grok.com/voice …")
    try:
        await bot.page.goto("https://grok.com/voice", wait_until="domcontentloaded", timeout=15_000)
        await asyncio.sleep(3)

        shot = await screenshot(bot.page, "02_voice_page")
        if shot:
            await interaction.followup.send(
                "📸 **Voice page:**",
                file=discord.File(shot, filename="voice_page.png"),
            )

        # The voice page loads with the mic active — no button click needed.
        # Verify it's showing the voice UI
        title = await bot.page.title()
        url   = bot.page.url
        log("nega", f"Voice page title='{title}' url='{url}'")

        # Fallback: try clicking the voice mode button if not on /voice already
        if "voice" not in url:
            selectors = [
                'button[aria-label="Enter voice mode (Ctrl+⇧O)"]',
                'button[aria-label*="voice mode" i]',
                'button[aria-label*="voice" i]',
            ]
            for sel in selectors:
                try:
                    el = await bot.page.wait_for_selector(sel, timeout=3000, state="visible")
                    if el:
                        await el.click()
                        log("nega", f"Clicked voice button via {sel} ✓")
                        await asyncio.sleep(3)
                        break
                except Exception:
                    pass

        # ── 5. Start audio bridge ─────────────────────────────────────────────
        await bot.bridge.start(vc)
        await interaction.followup.send(
            "🎙️ **Audio bridge active!**\n"
            "• Grok's voice → Discord VC ✓\n"
            "• Discord VC → Grok's mic ✓\n\n"
            "Use `/stop` to disconnect."
        )

    except Exception as e:
        log("nega", f"Error: {e}", "ERROR")
        shot = await screenshot(bot.page, "04_error")
        files = [discord.File(shot, "error.png")] if shot else []
        await interaction.followup.send(f"❌ خطأ: `{e}`", files=files)


@app_commands.command(name="stop", description="Stop the audio bridge and leave VC")
async def stop_cmd(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    vc = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if vc:
        await bot.bridge.stop(vc)
        await vc.disconnect()
        await interaction.followup.send("👋 Disconnected and bridge stopped.")
    else:
        await interaction.followup.send("⚠️ Not in a voice channel.")

# Register stop command
bot.tree.add_command  # registered in setup_hook below


# ─── events ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    if not discord.opus.is_loaded():
        try:
            discord.opus.load_opus("libopus.so.0")
            log("on_ready", "libopus loaded ✓")
        except Exception as e:
            log("on_ready", f"libopus load failed: {e}", "WARN")

    # Also sync /stop
    bot.tree.add_command(stop_cmd, guild=MY_GUILD)
    await bot.tree.sync(guild=MY_GUILD)
    log("on_ready", f"Bot online as {bot.user} ✓")


bot.run(BOT_TOKEN)
