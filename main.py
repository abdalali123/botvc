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

class GrokBot(commands.Bot):
    def __init__(self):
        # تفعيل الـ Intents بالكامل لضمان استقرار العمليات الصوتية
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
            
            # محاولة تحميل الكوكيز إذا كانت موجودة
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
            # تم تغيير الاسم لتجنب خطأ CommandSignatureMismatch
            print("--- 🔄 مزامنة الأوامر المائلة (Summon) ---")
            await self.tree.sync()
            print("--- ✅ النظام جاهز تماماً ---")
        except Exception as e:
            print(f"⚠️ فشل في إعداد النظام: {e}")

bot = GrokBot()

@bot.tree.command(
    name="summon", 
    description="استدعاء الظلال للانضمام إلى القناة الصوتية"
)
@app_commands.describe(phrase="اكتب 'my nega' لإتمام طقس الاستدعاء")
async def summon(interaction: discord.Interaction, phrase: str):
    """الأمر المحدث بـ Defer واسم جديد كلياً"""
    
    # 1. إخبار ديسكورد بالانتظار (هذا يحل مشكلة Application did not respond)
    await interaction.response.defer(thinking=True)
    
    if phrase.lower() == "my nega":
        if interaction.user.voice:
            try:
                # 2. الانضمام للقناة الصوتية
                channel = interaction.user.voice.channel
                
                # التحقق إذا كان البوت متصلاً بالفعل لتجنب الأخطاء
                voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
                if not voice_client:
                    await channel.connect()
                
                # 3. التفاعل مع واجهة Grok
                try:
                    # الانتظار حتى يظهر زر المايكروفون (المهلة 5 ثوانٍ)
                    await bot.page.wait_for_selector('button:has(div[class*="bg-fg-invert"])', timeout=5000)
                    await bot.page.click('button:has(div[class*="bg-fg-invert"])')
                except:
                    print("⚠️ لم يتم العثور على زر المايكروفون في صفحة Grok")

                # 4. الرد النهائي عبر الـ Followup بعد انتهاء العملية
                await interaction.followup.send("🌑 **The shadows obey... I have arrived.**")
                
            except Exception as e:
                await interaction.followup.send(f"❌ خطأ أثناء الانضمام: {e}")
        else:
            await interaction.followup.send("⚠️ يجب أن تكون داخل قناة صوتية أولاً ليتم الاستدعاء!")
    else:
        await interaction.followup.send("❓ العبارة غير صحيحة. حاول مجدداً.")

@bot.event
async def on_ready():
    # التأكد من جاهزية مكتبة Opus للصوت
    if not discord.opus.is_loaded():
        try:
            discord.opus.load_opus('libopus.so.0')
        except:
            pass
    print(f'✅ تم تسجيل الدخول بنجاح باسم: {bot.user}')

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ خطأ: لم يتم العثور على توكن البوت في الإعدادات!")
    else:
        bot.run(BOT_TOKEN)
