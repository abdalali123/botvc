import discord
from discord.ext import commands
import os
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# جلب التوكن من متغيرات البيئة في Railway
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.browser = None
        self.page = None

    async def setup_hook(self):
        print("--- جاري تشغيل المتصفح في الخلفية ---")
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=True, args=["--no-sandbox"])
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        await stealth_async(self.page)
        await self.page.goto("https://x.com/i/grok")
        print("--- البوت جاهز تماماً ---")

bot = GrokBot()

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"✅ انضممت إلى {channel.name}")
        # محاولة تفعيل المايك في Grok
        try:
            await bot.page.click('button:has(div[class*="bg-fg-invert"])')
        except:
            pass
    else:
        await ctx.send("❌ ادخل روم صوتي أولاً")

@bot.event
async def on_ready():
    print(f'✅ البوت يعمل الآن باسم: {bot.user}')

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
