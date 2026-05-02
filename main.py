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

class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.browser = None
        self.context = None
        self.page = None

    async def setup_hook(self):
        print("--- 🛠️  Setting up Playwright ---")
        try:
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            self.context = await self.browser.new_context()

            if os.path.exists('cookies.json'):
                with open('cookies.json', 'r') as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)

            self.page = await self.context.new_page()
            await stealth_async(self.page)

            # Don't await the page navigation here — do it in background
            asyncio.create_task(self._init_grok_page())

        except Exception as e:
            print(f"⚠️ Playwright setup failed: {e}")

        # ✅ FIX 1: Clear old global commands so /i disappears
        self.tree.clear_commands(guild=None)
        await self.tree.sync()  # push empty global list

        # ✅ FIX 2: Register commands to guild only, then sync
        self.tree.add_command(nega, guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)
        print(f"--- ✅ Guild commands synced to {MY_GUILD.id} ---")

    async def _init_grok_page(self):
        """Navigate to Grok in background so it doesn't block setup_hook"""
        try:
            await self.page.goto("https://x.com/i/grok")
            await asyncio.sleep(3)
            print("--- ✅ Grok page loaded ---")
        except Exception as e:
            print(f"⚠️ Could not load Grok page: {e}")


bot = GrokBot()

# ✅ FIX 3: Don't use @bot.tree.command here — add it manually in setup_hook above
# Define as a plain async function first, then register it
@app_commands.command(name="nega", description="Call the shadows to join your voice channel")
async def nega(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    if not interaction.user.voice:
        await interaction.followup.send("⚠️ Join a voice channel first!")
        return

    try:
        channel = interaction.user.voice.channel
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if not voice_client:
            await channel.connect()

        if bot.page:
            try:
                await bot.page.wait_for_selector('button:has(div[class*="bg-fg-invert"])', timeout=5000)
                await bot.page.click('button:has(div[class*="bg-fg-invert"])')
            except Exception:
                print("⚠️ Grok mic button not available")

        await interaction.followup.send("🌑 **The shadows obey... I have arrived.**")

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")


@bot.event
async def on_ready():
    if not discord.opus.is_loaded():
        try:
            discord.opus.load_opus('libopus.so.0')
        except Exception:
            pass
    print(f'✅ Connected as: {bot.user}')


bot.run(BOT_TOKEN)
