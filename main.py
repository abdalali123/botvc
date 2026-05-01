import discord
from discord.ext import commands
import json
import asyncio
import os
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# الإعدادات
# ملاحظة: إذا قمت بعمل Reset للتوكن، ضعه هنا فوراً
BOT_TOKEN = "MTQ5OTgzOTM1NTAxMzk1NTYzNA.G8I18t.8qjO3XLiOEbaVzi98bRuInQFlpRynfVsWYAZf4"
APP_ID = "1499839355013955634"

class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents, application_id=APP_ID)
        self.browser = None
        self.context = None
        self.page = None

    async def setup_hook(self):
        print("--- بدء تشغيل محرك المتصفح ---")
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
            
            print("--- التوجه إلى Grok ---")
            await self.page.goto("https://x.com/i/grok")
            await asyncio.sleep(2)
            print("--- النظام جاهز في الخلفية ---")
        except Exception as e:
            print(f"⚠️ فشل إعداد المتصفح: {e}")

bot = GrokBot()

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        try:
            channel = ctx.author.voice.channel
            await channel.connect()
            await ctx.send(f"✅ تم الانضمام لـ {channel.name}")
            # محاولة النقر على زر الصوت في Grok
            await bot.page.click('button:has(div[class*="bg-fg-invert"])')
        except Exception as e:
            await ctx.send(f"⚠️ خطأ: {e}")
    else:
        await ctx.send("⚠️ ادخل روم صوتي أولاً!")

@bot.event
async def on_ready():
    print(f'✅ البوت متصل الآن باسم: {bot.user}')

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
