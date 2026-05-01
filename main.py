import discord
from discord import app_commands # مكتبة الأوامر المائلة
from discord.ext import commands
import os
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

BOT_TOKEN = os.getenv("DISCORD_TOKEN")

class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        # نستخدم command_prefix فقط كاحتياط، الأساس سيكون الـ Slash
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
        
        # مزامنة الأوامر المائلة مع ديسكورد ليراها المستخدم عند ضغط /
        await self.tree.sync() 
        print("--- تم مزامنة Slash Commands بنجاح ---")

bot = GrokBot()

# تعريف الأمر المائل (Slash Command)
@bot.tree.command(name="summon", description="Summon the shadows to join your voice channel")
@app_commands.describe(my_nega="Type 'my nega' to complete the summon")
async def summon(interaction: discord.Interaction, my_nega: str):
    # التحقق من الجملة المدخلة
    if my_nega.lower() == "my nega":
        if interaction.user.voice:
            # يجب الرد على الـ Interaction أولاً
            await interaction.response.send_message("🌑 **The shadows obey... I have arrived.**")
            
            try:
                channel = interaction.user.voice.channel
                await channel.connect()
                
                # تفعيل المايك في Grok
                try:
                    await bot.page.click('button:has(div[class*="bg-fg-invert"])')
                except:
                    pass
            except Exception as e:
                await interaction.followup.send(f"⚠️ خطأ أثناء الاتصال: {e}")
        else:
            await interaction.response.send_message("⚠️ يجب أن تكون في قناة صوتية أولاً!")
    else:
        await interaction.response.send_message("❓ الجملة غير صحيحة. حاول استخدام: `my nega`")

@bot.event
async def on_ready():
    print(f'✅ البوت يعمل باسم: {bot.user}')

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
