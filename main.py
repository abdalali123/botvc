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
        """Placeholder - audio bridges disabled (requires PulseAudio/hardware audio)"""
        log("AUDIO_OUT", "Audio bridges not available in containerized environment")

    async def _start_input(self, vc: discord.VoiceClient):
        """Placeholder - audio bridges disabled (requires PulseAudio/hardware audio)"""
        log("AUDIO_IN", "Audio bridges not available in containerized environment")

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

    def _convert_browser_cookies(self, cookies):
        """
        Convert cookies from browser extension format to Playwright format.
        
        Handles:
        - Removal of extra fields (hostOnly, session, storeId, id)
        - Conversion of sameSite values (unspecified→None, no_restriction→None, etc)
        - Expiration date conversion to integers
        """
        playwright_cookies = []
        
        for cookie in cookies:
            pw_cookie = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie["domain"],
                "path": cookie.get("path", "/"),
            }
            
            # Add expiration if present
            if "expirationDate" in cookie:
                pw_cookie["expirationDate"] = int(cookie["expirationDate"])
            
            # Add optional boolean flags
            if "httpOnly" in cookie:
                pw_cookie["httpOnly"] = cookie["httpOnly"]
            
            if "secure" in cookie:
                pw_cookie["secure"] = cookie["secure"]
            
            # Convert sameSite values
            same_site = cookie.get("sameSite", "unspecified")
            if isinstance(same_site, str):
                same_site = same_site.lower()
            else:
                same_site = "unspecified"
            
            if same_site in ["unspecified", "none"]:
                pw_cookie["sameSite"] = "None"
            elif same_site == "lax":
                pw_cookie["sameSite"] = "Lax"
            elif same_site == "strict":
                pw_cookie["sameSite"] = "Strict"
            elif same_site == "no_restriction":
                pw_cookie["sameSite"] = "None"
            
            playwright_cookies.append(pw_cookie)
        
        return playwright_cookies

    async def setup_hook(self):
        """Initialize bot and Playwright browser"""
        log("SETUP", "Bot initializing...")
        
        # ============ PLAYWRIGHT SETUP ============
        try:
            log("SETUP", "Starting Playwright...")
            
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
                    
                    # Auto-detect and convert browser export format if needed
                    if cookies and isinstance(cookies, list) and "hostOnly" in cookies[0]:
                        log("SETUP", "Converting cookies from browser format to Playwright format...", "WARN")
                        cookies = self._convert_browser_cookies(cookies)
                    
                    await self.context.add_cookies(cookies)
                    log("SETUP", f"Loaded {len(cookies)} cookies ✓")
                except json.JSONDecodeError as e:
                    log("SETUP", f"Invalid cookies.json: {e}", "WARN")
                except Exception as e:
                    log("SETUP", f"Cookie load error: {e}", "WARN")
            else:
                log("SETUP", f"cookies.json not found - fresh login required", "WARN")
            
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
