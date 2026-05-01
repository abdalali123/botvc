import discord
from discord import app_commands 
from discord.ext import commands
import os
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# جلب التوكن من Variables في Railway
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
        
        # هذه الخطوة هي التي تجعل الأوامر تظهر عند ضغط /
        print("--- جاري مزامنة الأوامر مع ديسكورد ---")
        await self.tree.sync() 

bot = GrokBot()

# تعريف الأمر المائل المخصص الذي طلبته
@bot.tree.command(name="i", description="Summon the shadows")
@app_commands.describe(action="Type 'summon my nega' to perform the ritual")
async def summon(interaction: discord.Interaction, action: str):
    if action.lower() == "summon my nega":
        if interaction.user.voice:
            # الرد الفوري لإخبار المستخدم بنجاح الأمر
            await interaction.response.send_message("🌑 **The shadows obey... I have arrived.**")
            
            try:
                channel = interaction.user.voice.channel
                await channel.connect()
                
                # تفعيل المايك في واجهة Grok
                try:
                    await bot.page.click('button:has(div[class*="bg-fg-invert"])')
                except:
                    pass
            except Exception as e:
                await interaction.followup.send(f"⚠️ خطأ أثناء الانضمام: {e}")
        else:
            await interaction.response.send_message("⚠️ يجب أن تكون في قناة صوتية أولاً!")
    else:
        await interaction.response.send_message("❓ الجملة غير صحيحة، اكتب: `summon my nega`")

@bot.event
async def on_ready():
    print(f'✅ البوت جاهز تماماً باسم: {bot.user}')

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
