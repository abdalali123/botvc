import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# جلب التوكن من إعدادات Railway
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
# معرف السيرفر الخاص بك للمزامنة الفورية
MY_GUILD = discord.Object(id=1408448201555447968)

class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.browser = None
        self.context = None
        self.page = None

    async def setup_hook(self):
        """إعداد محرك المتصفح والأوامر عند تشغيل البوت"""
        print("--- 🛠️  جاري إعداد محرك Playwright ---")
        try:
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            self.context = await self.browser.new_context()
            
            # محاولة تحميل الكوكيز
            if os.path.exists('cookies.json'):
                with open('cookies.json', 'r') as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)
            
            self.page = await self.context.new_page()
            await stealth_async(self.page)
            
            await self.page.goto("https://x.com/i/grok")
            await asyncio.sleep(2)
            
            # مزامنة الأوامر المائلة للسيرفر المحدد فقط (فورية)
            print(f"--- 🔄 مزامنة الأمر الجديد /nega للسيرفر: {MY_GUILD.id} ---")
            self.tree.copy_from(guild=MY_GUILD) # نسخ الأوامر للسيرفر
            await self.tree.sync(guild=MY_GUILD)
            print("--- ✅ المزامنة الفورية اكتملت ---")
        except Exception as e:
            print(f"⚠️ فشل في إعداد النظام: {e}")

bot = GrokBot()

@bot.tree.command(
    name="nega", 
    description="استدعاء الظلال للانضمام إلى القناة الصوتية"
)
async def nega(interaction: discord.Interaction):
    """الأمر النهائي بـ Defer ومزامنة فورية"""
    
    # 1. إخبار ديسكورد بالانتظار (يحل مشكلة Application did not respond)
    await interaction.response.defer(thinking=True)
    
    if interaction.user.voice:
        try:
            # 2. الانضمام للقناة الصوتية
            channel = interaction.user.voice.channel
            
            voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
            if not voice_client:
                await channel.connect()
            
            # 3. التفاعل مع واجهة Grok
            try:
                await bot.page.wait_for_selector('button:has(div[class*="bg-fg-invert"])', timeout=5000)
                await bot.page.click('button:has(div[class*="bg-fg-invert"])')
            except:
                print("⚠️ زر المايك غير متاح في صفحة Grok")

            # 4. الرد النهائي
            await interaction.followup.send("🌑 **The shadows obey... I have arrived.**")
            
        except Exception as e:
            await interaction.followup.send(f"❌ خطأ أثناء الاستدعاء: {e}")
    else:
        await interaction.followup.send("⚠️ ادخل قناة صوتية أولاً!")

@bot.event
async def on_ready():
    if not discord.opus.is_loaded():
        try:
            discord.opus.load_opus('libopus.so.0')
        except:
            pass
    print(f'✅ متصل الآن باسم: {bot.user}')

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
