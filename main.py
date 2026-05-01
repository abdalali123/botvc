import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# جلب التوكن من Variables في Railway
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.browser = None
        self.context = None
        self.page = None

    async def setup_hook(self):
        """إعداد المتصفح عند بدء تشغيل البوت"""
        print("--- 🛠️  إعداد محرك Playwright ---")
        try:
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            self.context = await self.browser.new_context()
            
            # محاولة تحميل الكوكيز لضمان تسجيل الدخول
            if os.path.exists('cookies.json'):
                with open('cookies.json', 'r') as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)
            
            self.page = await self.context.new_page()
            await stealth_async(self.page)
            
            print("--- 🌐 التوجه إلى صفحة Grok ---")
            await self.page.goto("https://x.com/i/grok")
            await asyncio.sleep(2)
            
            # مزامنة الأوامر المائلة (Slash Commands)
            print("--- 🔄 مزامنة الأوامر المائلة ---")
            await self.tree.sync()
            print("--- ✅ البوت جاهز تماماً ---")
        except Exception as e:
            print(f"⚠️ فشل في إعداد النظام: {e}")

bot = GrokBot()

@bot.tree.command(
    name="i", 
    description="استدعاء الظلال للانضمام إلى القناة الصوتية"
)
@app_commands.describe(summon="اكتب 'my nega' لإتمام طقس الاستدعاء")
async def i(interaction: discord.Interaction, summon: str):
    """الأمر الرئيسي المحدث مع خاصية Defer لتجنب المهلة"""
    
    # 1. إخبار ديسكورد بالانتظار (يفيد في العمليات الطويلة مثل Playwright)
    await interaction.response.defer(thinking=True)
    
    if summon.lower() == "my nega":
        if interaction.user.voice:
            try:
                # 2. الانضمام للقناة الصوتية (يتطلب مكتبة DAVE المشفرة)
                channel = interaction.user.voice.channel
                
                # التحقق إذا كان البوت متصلاً بالفعل
                voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
                if not voice_client:
                    await channel.connect()
                
                # 3. محاكاة تفعيل المايك في صفحة Grok
                try:
                    # ننتظر الزر ليصبح متاحاً ثم نضغط
                    await bot.page.wait_for_selector('button:has(div[class*="bg-fg-invert"])', timeout=5000)
                    await bot.page.click('button:has(div[class*="bg-fg-invert"])')
                except:
                    print("⚠️ زر المايك غير متاح حالياً في المتصفح")

                # 4. الرد النهائي بعد اكتمال المهمة
                await interaction.followup.send("🌑 **The shadows obey... I have arrived.**")
                
            except Exception as e:
                await interaction.followup.send(f"❌ خطأ أثناء الاستدعاء: {e}")
        else:
            await interaction.followup.send("⚠️ ادخل قناة صوتية أولاً ليتم الاستدعاء!")
    else:
        await interaction.followup.send("❓ كلمة السر غير صحيحة.")

@bot.event
async def on_ready():
    # التأكد من تحميل Opus للصوت
    if not discord.opus.is_loaded():
        try:
            discord.opus.load_opus('libopus.so.0')
        except:
            pass
    print(f'✅ Logged in as: {bot.user}')

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
