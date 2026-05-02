import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

BOT_TOKEN = os.getenv("DISCORD_TOKEN")
MY_GUILD = discord.Object(id=1408448201555447968)

# ─── helpers ──────────────────────────────────────────────────────────────────
def log(step: str, msg: str, level: str = "INFO"):
    print(f"[{level}] [{step}] {msg}", flush=True)

async def screenshot(page, name: str):
    """Save a screenshot for debugging and print its path."""
    path = f"/tmp/debug_{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        log("screenshot", f"Saved → {path}")
    except Exception as e:
        log("screenshot", f"Failed to save {path}: {e}", "WARN")

# ─── bot class ────────────────────────────────────────────────────────────────
class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.browser = None
        self.context = None
        self.page = None
        self.grok_ready = False   # flipped to True once the page is usable

    # ── boot ──────────────────────────────────────────────────────────────────
    async def setup_hook(self):
        log("setup_hook", "Starting Playwright …")
        try:
            self.pw = await async_playwright().start()
            log("setup_hook", "Playwright started ✓")

            self.browser = await self.pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            log("setup_hook", "Browser launched ✓")

            self.context = await self.browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            log("setup_hook", "Browser context created ✓")

            # load cookies
            if os.path.exists("cookies.json"):
                with open("cookies.json", "r") as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)
                log("setup_hook", f"Loaded {len(cookies)} cookies ✓")
            else:
                log("setup_hook", "No cookies.json found — will likely hit login wall", "WARN")

            self.page = await self.context.new_page()
            await stealth_async(self.page)
            log("setup_hook", "Stealth applied ✓")

            # navigate in background so command sync isn't blocked
            asyncio.create_task(self._load_grok())

        except Exception as e:
            log("setup_hook", f"Browser setup FAILED: {e}", "ERROR")

        # ── sync commands ──────────────────────────────────────────────────
        log("setup_hook", "Clearing stale global commands …")
        self.tree.clear_commands(guild=None)
        await self.tree.sync()
        log("setup_hook", "Global commands cleared ✓")

        self.tree.add_command(nega, guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)
        log("setup_hook", f"Guild command /nega synced to {MY_GUILD.id} ✓")

    # ── grok page loader ──────────────────────────────────────────────────────
    async def _load_grok(self):
        log("grok_load", "Navigating to https://x.com/i/grok …")
        try:
            response = await self.page.goto(
                "https://x.com/i/grok",
                wait_until="domcontentloaded",
                timeout=30_000
            )
            log("grok_load", f"Page responded with HTTP {response.status}")
            await asyncio.sleep(4)   # let JS hydrate

            url = self.page.url
            log("grok_load", f"Current URL after load: {url}")
            await screenshot(self.page, "01_after_load")

            if "login" in url or "signin" in url:
                log("grok_load", "Redirected to login — cookies may be stale!", "WARN")
                self.grok_ready = False
                return

            title = await self.page.title()
            log("grok_load", f"Page title: {title}")
            self.grok_ready = True
            log("grok_load", "Grok page READY ✓")

        except Exception as e:
            log("grok_load", f"Navigation error: {e}", "ERROR")
            self.grok_ready = False


# ─── instantiate bot ──────────────────────────────────────────────────────────
bot = GrokBot()


# ─── /nega command ────────────────────────────────────────────────────────────
@app_commands.command(name="nega", description="Call the shadows to join your voice channel")
async def nega(interaction: discord.Interaction):
    log("nega", f"Called by {interaction.user} in guild {interaction.guild_id}")
    await interaction.response.defer(thinking=True)

    # ── 1. voice check ────────────────────────────────────────────────────────
    if not interaction.user.voice:
        log("nega", "User is not in a voice channel", "WARN")
        await interaction.followup.send("⚠️ Join a voice channel first!")
        return
    log("nega", f"User is in channel: {interaction.user.voice.channel.name}")

    # ── 2. join VC ────────────────────────────────────────────────────────────
    try:
        channel = interaction.user.voice.channel
        vc = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if not vc:
            log("nega", f"Connecting to '{channel.name}' …")
            vc = await channel.connect()
            log("nega", "Voice connection established ✓")
        else:
            log("nega", "Already connected to a voice channel ✓")
    except Exception as e:
        log("nega", f"Voice connect error: {e}", "ERROR")
        await interaction.followup.send(f"❌ Could not join voice channel: `{e}`")
        return

    # ── 3. grok readiness ────────────────────────────────────────────────────
    if not bot.grok_ready or bot.page is None:
        log("nega", "Grok page not ready — skipping browser interaction", "WARN")
        await interaction.followup.send(
            "🌑 **Joined your channel, but Grok isn't ready yet.** "
            "Check Railway logs for screenshot paths."
        )
        return

    # ── 4. Grok interaction ───────────────────────────────────────────────────
    log("nega", "Starting Grok browser interaction …")
    try:
        # make sure we're still on the right page
        current_url = bot.page.url
        log("nega", f"Current page URL: {current_url}")

        if "grok" not in current_url:
            log("nega", "Not on Grok page — reloading …", "WARN")
            await bot.page.goto("https://x.com/i/grok", wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(3)

        await screenshot(bot.page, "02_before_click")

        # ── dump ALL buttons so we can see what's available ──────────────────
        log("nega", "Enumerating all <button> elements on page …")
        buttons_info = await bot.page.evaluate("""
            () => {
                const btns = [...document.querySelectorAll('button')];
                return btns.slice(0, 30).map((b, i) => ({
                    index: i,
                    text: b.innerText.trim().slice(0, 60),
                    ariaLabel: b.getAttribute('aria-label') || '',
                    className: b.className.slice(0, 80),
                    visible: b.offsetParent !== null
                }));
            }
        """)
        for btn in buttons_info:
            log("nega", f"  btn[{btn['index']}] visible={btn['visible']} "
                        f"text='{btn['text']}' aria='{btn['ariaLabel']}' "
                        f"class='{btn['className'][:40]}'")

        # ── try multiple selectors in order ──────────────────────────────────
        selectors = [
            # aria-label based (most stable)
            'button[aria-label*="microphone" i]',
            'button[aria-label*="voice" i]',
            'button[aria-label*="audio" i]',
            # class-based (brittle but worth trying)
            'button:has(div[class*="bg-fg-invert"])',
            # SVG mic icon inside button
            'button:has(svg[data-testid*="mic" i])',
            'button:has(svg[aria-label*="mic" i])',
        ]

        clicked = False
        for sel in selectors:
            log("nega", f"Trying selector: {sel}")
            try:
                el = await bot.page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    box = await el.bounding_box()
                    log("nega", f"  → Found! Bounding box: {box}")
                    await el.click()
                    log("nega", f"  → Clicked ✓")
                    clicked = True
                    break
            except Exception as sel_err:
                log("nega", f"  → Not found ({sel_err})")

        await asyncio.sleep(1)
        await screenshot(bot.page, "03_after_click")

        if clicked:
            msg = "🌑 **The shadows obey... I have arrived.**"
        else:
            log("nega", "No mic button found — joined VC but couldn't trigger Grok", "WARN")
            msg = (
                "🌑 **Joined the channel** — but I couldn't find Grok's mic button.\n"
                "Check Railway logs: look for `debug_02_before_click.png` and the button list."
            )

        await interaction.followup.send(msg)

    except Exception as e:
        log("nega", f"Grok interaction error: {e}", "ERROR")
        await screenshot(bot.page, "04_error_state")
        await interaction.followup.send(f"❌ Grok browser error: `{e}`")


# ─── events ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    if not discord.opus.is_loaded():
        try:
            discord.opus.load_opus("libopus.so.0")
            log("on_ready", "libopus loaded ✓")
        except Exception as e:
            log("on_ready", f"libopus load failed (voice may not work): {e}", "WARN")
    log("on_ready", f"Bot online as {bot.user} ✓")


bot.run(BOT_TOKEN)
