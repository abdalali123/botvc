import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
from playwright.async_api import async_playwright

BOT_TOKEN = os.getenv("DISCORD_TOKEN")
MY_GUILD = discord.Object(id=1408448201555447968)

# ─── helpers ──────────────────────────────────────────────────────────────────
def log(step: str, msg: str, level: str = "INFO"):
    print(f"[{level}] [{step}] {msg}", flush=True)

async def screenshot(page, name: str) -> "str | None":
    """Save a screenshot and return its path (or None on failure)."""
    path = f"/tmp/debug_{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        log("screenshot", f"Saved → {path}")
        return path
    except Exception as e:
        log("screenshot", f"Failed to save {path}: {e}", "WARN")
        return None

# ─── bot class ────────────────────────────────────────────────────────────────
class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.browser = None
        self.context = None
        self.page = None
        self.grok_ready = False

    # ── boot ──────────────────────────────────────────────────────────────────
    async def setup_hook(self):
        log("setup_hook", "Starting Playwright …")
        try:
            self.pw = await async_playwright().start()
            log("setup_hook", "Playwright started ✓")

            # Anti-detection via browser args — no external stealth library needed
            self.browser = await self.pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",  # hides webdriver flag
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",                           # no extensions = no conflict
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--window-size=1280,800",
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                ]
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
            log("setup_hook", "Browser context created ✓")

            # Patch navigator.webdriver = false at the JS level
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)
            log("setup_hook", "JS anti-detection patches applied ✓")

            # load cookies
            if os.path.exists("cookies.json"):
                with open("cookies.json", "r") as f:
                    raw_cookies = json.load(f)

                SAMESITE_MAP = {
                    "unspecified":    "None",
                    "no_restriction": "None",
                    "lax":            "Lax",
                    "strict":         "Strict",
                    "none":           "None",
                }
                STRIP_FIELDS = {"hostOnly", "session", "storeId", "id"}

                cookies = []
                for c in raw_cookies:
                    fixed = {k: v for k, v in c.items() if k not in STRIP_FIELDS}
                    raw_ss = str(fixed.get("sameSite", "None")).lower()
                    fixed["sameSite"] = SAMESITE_MAP.get(raw_ss, "None")
                    cookies.append(fixed)

                await self.context.add_cookies(cookies)
                log("setup_hook", f"Loaded {len(cookies)} cookies (sameSite sanitised) ✓")
            else:
                log("setup_hook", "No cookies.json found — will likely hit login wall", "WARN")

            self.page = await self.context.new_page()
            log("setup_hook", "Page created ✓")

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
        log("grok_load", "Navigating to https://grok.com …")
        try:
            response = await self.page.goto(
                "https://grok.com",
                wait_until="domcontentloaded",
                timeout=30_000
            )
            log("grok_load", f"Page responded with HTTP {response.status}")
            await asyncio.sleep(5)   # let JS hydrate fully

            # ── retry loop: handle "Something went wrong" error screen ────────
            for attempt in range(3):
                url = self.page.url
                log("grok_load", f"[attempt {attempt+1}] URL: {url}")

                # Check for the error page text
                try:
                    error_text = await self.page.locator("text=Something went wrong").count()
                except Exception:
                    error_text = 0

                if error_text > 0:
                    log("grok_load", "Error page detected — clicking 'Try again' …", "WARN")
                    try:
                        await self.page.click("text=Try again", timeout=5000)
                        await asyncio.sleep(5)
                    except Exception as e:
                        log("grok_load", f"Could not click Try again: {e}", "WARN")
                    continue  # re-check

                # Check for login redirect
                if "login" in url or "signin" in url:
                    log("grok_load", "Redirected to login — cookies may be stale!", "WARN")
                    await screenshot(self.page, "01_login_redirect")
                    self.grok_ready = False
                    return

                # Page looks good — break out
                break

            await screenshot(self.page, "01_after_load")
            title = await self.page.title()
            log("grok_load", f"Page title: '{title}'")

            # Final check
            final_url = self.page.url
            if "login" in final_url or "signin" in final_url:
                log("grok_load", "Still on login page after retries!", "ERROR")
                self.grok_ready = False
                return

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
            await bot.page.goto("https://grok.com", wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(3)

        # ── screenshot BEFORE and send to Discord immediately ────────────────
        shot_before = await screenshot(bot.page, "02_before_click")
        if shot_before:
            await interaction.followup.send(
                "📸 **صورة الصفحة الآن** (قبل أي ضغط):",
                file=discord.File(shot_before, filename="grok_page.png")
            )

        # ── dump ALL buttons so we can see what's available ──────────────────
        log("nega", "Enumerating all <button> elements on page …")
        buttons_info = await bot.page.evaluate("""
            () => {
                const btns = [...document.querySelectorAll('button')];
                return btns.slice(0, 40).map((b, i) => ({
                    index: i,
                    text: b.innerText.trim().slice(0, 60),
                    ariaLabel: b.getAttribute('aria-label') || '',
                    className: b.className.slice(0, 80),
                    visible: b.offsetParent !== null
                }));
            }
        """)

        # Build a readable text summary for Discord
        btn_lines = ["```"]
        for btn in buttons_info:
            vis = "✓" if btn["visible"] else "✗"
            btn_lines.append(
                f"[{btn['index']:02d}] vis={vis} "
                f"aria='{btn['ariaLabel']}' "
                f"text='{btn['text'][:30]}'"
            )
            log("nega", f"  btn[{btn['index']}] visible={btn['visible']} "
                        f"aria='{btn['ariaLabel']}' text='{btn['text']}'")
        btn_lines.append("```")
        btn_summary = "\n".join(btn_lines)

        # Send button list to Discord (split if too long)
        if len(btn_summary) <= 2000:
            await interaction.followup.send(f"🔍 **الأزرار الموجودة في الصفحة:**\n{btn_summary}")
        else:
            await interaction.followup.send(f"🔍 **الأزرار الموجودة في الصفحة:**\n{btn_summary[:1990]}…```")

        # ── try multiple selectors in order ──────────────────────────────────
        selectors = [
            'button[aria-label="Enter voice mode"]',   # confirmed from page scan
            'button[aria-label*="voice mode" i]',
            'button[aria-label*="microphone" i]',
            'button[aria-label*="voice" i]',
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
                log("nega", f"  → Not found ({type(sel_err).__name__})")

        # Wait longer for voice mode to attempt connection
        await asyncio.sleep(4)

        # ── diagnose WHY voice mode fails ────────────────────────────────────
        diag = await bot.page.evaluate("""
            async () => {
                const info = {};
                try {
                    const devices = await navigator.mediaDevices.enumerateDevices();
                    info.audioInputs = devices.filter(d => d.kind === 'audioinput').map(d => d.label || d.deviceId).join(', ') || 'none found';
                } catch(e) { info.audioInputs = 'ERROR: ' + e.message; }

                try {
                    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
                    info.micStream = 'OK - tracks: ' + stream.getAudioTracks().length;
                    stream.getTracks().forEach(t => t.stop());
                } catch(e) { info.micStream = 'FAILED: ' + e.message; }

                try {
                    const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:stun.l.google.com:19302'}]});
                    const offer = await pc.createOffer({offerToReceiveAudio: true});
                    await pc.setLocalDescription(offer);
                    await new Promise(r => setTimeout(r, 2500));
                    const sdp = pc.localDescription ? pc.localDescription.sdp : '';
                    info.iceCandidates = sdp.split('\\n').filter(l => l.startsWith('a=candidate')).length + ' candidates';
                    pc.close();
                } catch(e) { info.iceCandidates = 'ERROR: ' + e.message; }

                const errEl = document.querySelector('[class*="error"], [class*="Error"]');
                info.pageError = errEl ? errEl.innerText.slice(0, 150) : 'none visible';
                return info;
            }
        """)

        diag_lines = ["```"]
        for k, v in diag.items():
            diag_lines.append(f"{k}: {v}")
        diag_lines.append("```")
        log("nega", f"Diagnostics: {diag}")
        await interaction.followup.send("🔬 **تشخيص WebRTC/صوت:**\n" + "\n".join(diag_lines))

        shot_after = await screenshot(bot.page, "03_after_click")
        if shot_after:
            await interaction.followup.send("📸 **بعد الضغط:**", file=discord.File(shot_after, filename="grok_after.png"))

        if clicked:
            await interaction.followup.send(
                "✅ الزر اشتغل — لكن Grok رفض الاتصال.\n"
                "• `micStream: FAILED` = مشكلة إذن ميكروفون\n"
                "• `iceCandidates: 0` = Railway يحجب UDP/WebRTC"
            )
        else:
            await interaction.followup.send("⚠️ ما لقيت زر voice mode.")

    except Exception as e:
        log("nega", f"Grok interaction error: {e}", "ERROR")
        shot_err = await screenshot(bot.page, "04_error_state")
        files = [discord.File(shot_err, filename="error_state.png")] if shot_err else []
        await interaction.followup.send(f"❌ خطأ: `{e}`", files=files)


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
