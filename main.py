import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# جلب التوكن من إعدادات Railway (Environment Variables)
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

class GrokBot(commands.Bot):
    def __init__(self):
        # تفعيل جميع الـ Intents لضمان وصول البوت لكل البيانات
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.browser = None
        self.context = None
        self.page = None

    async def setup_hook(self):
        """يتم تشغيل هذه الدالة عند بدء تشغيل البوت لإعداد المتصفح والأوامر"""
        print("--- 🛠️  بدء تشغيل محرك المتصفح (Playwright) ---")
        try:
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            self.context = await self.browser.new_context()
            
            # محاولة تحميل الكوكيز إذا كانت موجودة لضمان بقاء الحساب مسجلاً
            if os.path.exists('cookies.json'):
                with open('cookies.json', 'r') as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)
            
            self.page = await self.context.new_page()
            await stealth_async(self.page)
            
            print("--- 🌐 التوجه إلى صفحة Grok ---")
            await self.page.goto("https://x.com/i/grok")
            await asyncio.sleep(2)
            
            # مزامنة الأوامر المائلة (Slash Commands) مع ديسكورد
            print("--- 🔄 مزامنة الأوامر المائلة (Slash Commands) ---")
            await self.tree.sync()
            print("--- ✅ النظام جاهز تماماً ---")
        except Exception as e:
            print(f"⚠️ فشل في إعداد النظام: {e}")

bot = GrokBot()

# --- تعريف الأمر المائل المخصص (Slash Command) ---
@bot.tree.command(
    name="i", 
    description="استدعاء الظلال للانضمام إلى القناة الصوتية"
)
@app_commands.describe(summon="اكتب 'my nega' لإتمام طقس الاستدعاء")
async def i(interaction: discord.Interaction, summon: str):
    # التحقق من الجملة المدخلة (Summon ritual)
    if summon.lower() == "my nega":
        if interaction.user.voice:
            # الرد الفوري على ديسكورد
            await interaction.response.send_message("🌑 **The shadows obey... I have arrived.**")
            
            try:
                # الانضمام إلى القناة الصوتية
                channel = interaction.user.voice.channel
                await channel.connect()
                
                # التفاعل مع واجهة Grok لتفعيل الصوت
                # ملاحظة: الكود يبحث عن زر المايكروفون بناءً على كلاسات X الحالية
                try:
                    await bot.page.click('button:has(div[class*="bg-fg-invert"])')
                except:
                    print("⚠️ لم يتم العثور على زر المايكروفون في صفحة Grok")
            except Exception as e:
                await interaction.followup.send(f"❌ خطأ أثناء الانضمام: {e}")
        else:
            await interaction.response.send_message("⚠️ يجب أن تكون داخل قناة صوتية أولاً ليتم الاستدعاء!")
    else:
        await interaction.response.send_message("❓ الجملة غير صحيحة. حاول كتابة: `my nega`")

@bot.event
async def on_ready():
    # التأكد من تحميل مكتبة الصوت (Opus) اللازمة لتجاوز خطأ التشفير
    if not discord.opus.is_loaded():
        try:
            discord.opus.load_opus('libopus.so.0')
            print("🎵 تم تحميل مكتبة الصوت Opus بنجاح.")
        except Exception as e:
            print(f"⚠️ تحذير: فشل تحميل Opus: {e}")
            
    print(f'✅ تم تسجيل الدخول بنجاح باسم: {bot.user}')

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ خطأ فادح: لم يتم العثور على DISCORD_TOKEN في إعدادات Railway!")
    else:
        bot.run(BOT_TOKEN)
