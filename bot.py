import logging
import aiohttp
import asyncio
import openai
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.dispatcher.storage import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.middlewares.logging import LoggingMiddleware
import time
from datetime import datetime, timedelta

# Konfigurasi API langsung (tanpa env)
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Ganti dengan token bot kamu
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Ganti dengan API key OpenAI kamu
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")  # Ganti dengan API token Replicate kamu

# Config lainnya
MAX_DAILY_USES = 10  # Maksimum penggunaan per hari
POLLING_TIMEOUT = 120  # Timeout dalam detik untuk polling API
POLL_INTERVAL = 2  # Interval polling dalam detik

# Setup
openai.api_key = OPENAI_API_KEY
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Inisialisasi bot dengan storage
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# User rate limit tracking
user_usage = {}  # {user_id: {"count": 0, "reset_time": timestamp}}

# States untuk style selection
class GenerateStates(StatesGroup):
    choosing_style = State()
    entering_prompt = State()

# Model options
MODELS = {
    "sdxl": "a9758cbf0e03a7e926ef5f115cb50910588f94b21e8c967c88d8f4c576f3d9a3",
    "realistic": "b9130e53d15b99122a1c36d55f487e28f3fe59e1df3c280e0c7f3b01b57eb5e5",
    "anime": "40c519a5e622dd677550848d4b8966b9c73243e53a499a0cabc11afeaf268f33"
}

# Check rate limit
def check_rate_limit(user_id):
    current_time = time.time()
    
    # Reset penghitung jika hari baru
    if user_id in user_usage:
        last_reset = user_usage[user_id]["reset_time"]
        # Reset jika sudah 24 jam
        if current_time - last_reset > 86400:  # 24 jam dalam detik
            user_usage[user_id] = {"count": 0, "reset_time": current_time}
    else:
        user_usage[user_id] = {"count": 0, "reset_time": current_time}
    
    # Check limit
    if user_usage[user_id]["count"] >= MAX_DAILY_USES:
        return False
    
    # Increment counter
    user_usage[user_id]["count"] += 1
    return True

# /start command dengan UI yang bagus
@dp.message_handler(commands=["start"])
async def start_handler(msg: types.Message):
    user_name = msg.from_user.first_name
    text = (
        f"✨ **Selamat datang {user_name} di AI Image Bot!** ✨\n\n"
        "Buat gambar AI dari imajinasi kamu dalam hitungan detik.\n\n"
        "**Fitur utama:**\n"
        "• `/generate` – Buat gambar dari teks (dengan pemilihan style)\n"
        "• `/textgen <prompt>` – Perbaiki prompt agar lebih cocok untuk AI\n"
        "• `/usage` - Cek sisa kuota harian kamu\n\n"
        "Klik tombol di bawah ini untuk bantuan, support, atau hubungi owner."
    )

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📘 Help - Cara Pakai", callback_data="help")
    )
    keyboard.add(
        InlineKeyboardButton("🛟 Support", url="http://t.me/ariaxsupportbot"),
        InlineKeyboardButton("👤 Owner", url="https://t.me/sambunvg")
    )

    await msg.reply(text, reply_markup=keyboard, parse_mode="Markdown")

# Callback untuk tombol Help
@dp.callback_query_handler(lambda c: c.data == 'help')
async def help_callback(callback_query: types.CallbackQuery):
    help_text = (
        "**Cara Menggunakan Bot:**\n\n"
        "`/generate` - Buat gambar dengan memilih style terlebih dahulu\n"
        "`/textgen <prompt>` - Perbaiki prompt supaya AI lebih paham\n"
        "`/usage` - Cek sisa kuota harian kamu\n\n"
        "**Tips untuk prompt yang bagus:**\n"
        "• Jelaskan dengan detail (subjek, latar, pencahayaan)\n"
        "• Sebutkan style yang diinginkan (photorealistic, anime, dll)\n"
        "• Gunakan bahasa Inggris untuk hasil terbaik\n\n"
        "Contoh prompt bagus:\n"
        "`a majestic tiger in a cyberpunk city, neon lights, detailed, 8k, cinematic lighting`"
    )
    await callback_query.answer()
    await bot.send_message(callback_query.from_user.id, help_text, parse_mode="Markdown")

# Cek penggunaan harian
@dp.message_handler(commands=["usage"])
async def usage_handler(msg: types.Message):
    user_id = msg.from_user.id
    
    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0, "reset_time": time.time()}
    
    count = user_usage[user_id]["count"]
    reset_time = user_usage[user_id]["reset_time"]
    next_reset = datetime.fromtimestamp(reset_time) + timedelta(days=1)
    
    remaining = MAX_DAILY_USES - count
    
    text = (
        f"📊 **Penggunaan Harian Kamu**\n\n"
        f"• Penggunaan: {count}/{MAX_DAILY_USES}\n"
        f"• Sisa kuota: {remaining} permintaan\n"
        f"• Reset pada: {next_reset.strftime('%d %b %Y, %H:%M')}"
    )
    
    await msg.reply(text, parse_mode="Markdown")

# /textgen pakai GPT
@dp.message_handler(commands=["textgen"])
async def textgen_handler(msg: types.Message):
    user_id = msg.from_user.id
    
    # Check rate limit
    if not check_rate_limit(user_id):
        await msg.reply("⚠️ Kamu telah mencapai batas penggunaan harian. Coba lagi besok atau hubungi owner untuk upgrade.")
        return
    
    user_prompt = msg.get_args()
    if not user_prompt:
        await msg.reply("Contoh: /textgen kucing lucu di luar angkasa")
        return

    progress_msg = await msg.reply("⏳ Memproses prompt...")
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Perbaiki prompt ini agar lebih jelas untuk AI image generator. Tambahkan detail, style, pencahayaan, dan elemen yang membuat gambar lebih bagus. Gunakan bahasa Inggris untuk hasil terbaik."},
                {"role": "user", "content": user_prompt}
            ]
        )
        improved = res['choices'][0]['message']['content']
        await progress_msg.delete()
        await msg.reply(f"✅ **Prompt disempurnakan:**\n\n`{improved.strip()}`\n\nKlik untuk menyalin.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"OpenAI Error: {e}")
        await progress_msg.delete()
        await msg.reply(f"❌ Gagal memperbaiki prompt. Silakan coba lagi nanti.")

# Begin generate process - pilih style dulu
@dp.message_handler(commands=["generate"])
async def start_generate(msg: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🌟 Standard (SDXL)", callback_data="style_sdxl"),
        InlineKeyboardButton("📸 Realistic", callback_data="style_realistic"),
        InlineKeyboardButton("🎨 Anime", callback_data="style_anime")
    )
    await msg.reply("Pilih style gambar yang kamu inginkan:", reply_markup=keyboard)

# Callback untuk style selection
@dp.callback_query_handler(lambda c: c.data.startswith('style_'))
async def style_callback(callback_query: types.CallbackQuery, state: FSMContext):
    style = callback_query.data.split('_')[1]
    
    # Simpan style untuk langkah berikutnya
    await state.update_data(style=style)
    await GenerateStates.entering_prompt.set()
    
    style_names = {
        "sdxl": "Standard (SDXL)",
        "realistic": "Realistic",
        "anime": "Anime"
    }
    
    await callback_query.answer()
    await bot.send_message(
        callback_query.from_user.id, 
        f"Style dipilih: **{style_names[style]}**\n\nSekarang ketik prompt gambar yang kamu inginkan:",
        parse_mode="Markdown"
    )

# Handle prompt setelah memilih style
@dp.message_handler(state=GenerateStates.entering_prompt)
async def generate_with_style(msg: types.Message, state: FSMContext):
    user_id = msg.from_user.id
    
    # Check rate limit
    if not check_rate_limit(user_id):
        await state.finish()
        await msg.reply("⚠️ Kamu telah mencapai batas penggunaan harian. Coba lagi besok atau hubungi owner untuk upgrade.")
        return
    
    # Dapatkan data style dari state
    data = await state.get_data()
    style = data.get("style", "sdxl")
    model_id = MODELS[style]
    
    # Reset state
    await state.finish()
    
    prompt = msg.text
    if not prompt or len(prompt) < 3:
        await msg.reply("Prompt terlalu pendek. Berikan deskripsi yang lebih detail.")
        return

    progress_msg = await msg.reply("🎨 Sedang membuat gambar... (0%)")

    url = "https://api.replicate.com/v1/predictions"
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "version": model_id,
        "input": {
            "prompt": prompt
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            # Kirim request ke Replicate
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 201:
                    error_text = await resp.text()
                    logger.error(f"Replicate error: {error_text}")
                    await progress_msg.edit_text("❌ Gagal menghubungi server. Coba lagi nanti.")
                    return
                response = await resp.json()
                prediction_url = response["urls"]["get"]

            # Polling sampai hasil jadi dengan progress updates
            start_time = time.time()
            status = "starting"
            progress_updates = ["⏳ Sedang membuat gambar... (25%)", 
                              "⏳ Sedang membuat gambar... (50%)", 
                              "⏳ Sedang membuat gambar... (75%)"]
            update_index = 0
            
            while status not in ["succeeded", "failed"]:
                # Timeout check
                if time.time() - start_time > POLLING_TIMEOUT:
                    await progress_msg.edit_text("❌ Permintaan timeout. Coba lagi nanti.")
                    return
                
                # Progress updates
                elapsed = time.time() - start_time
                if elapsed > (update_index + 1) * (POLLING_TIMEOUT/4) and update_index < 3:
                    await progress_msg.edit_text(progress_updates[update_index])
                    update_index += 1
                
                # Poll API
                async with session.get(prediction_url, headers=headers) as poll:
                    if poll.status != 200:
                        await progress_msg.edit_text("❌ Gagal mendapatkan status gambar.")
                        return
                    
                    result = await poll.json()
                    status = result["status"]
                    
                    if status == "succeeded":
                        image_url = result["output"][0]
                        await progress_msg.delete()
                        
                        # Buat tombol untuk generate lagi
                        keyboard = InlineKeyboardMarkup()
                        keyboard.add(
                            InlineKeyboardButton("🔄 Generate Lagi", callback_data="new_generate")
                        )
                        
                        await msg.reply_photo(
                            photo=image_url, 
                            caption=f"🎨 **Gambar selesai!**\n\nPrompt: `{prompt}`", 
                            parse_mode="Markdown",
                            reply_markup=keyboard
                        )
                        return
                    elif status == "failed":
                        error = result.get("error", "Unknown error")
                        logger.error(f"Generation failed: {error}")
                        await progress_msg.edit_text(f"❌ Gagal menghasilkan gambar: {error}")
                        return
                
                # Wait before polling again
                await asyncio.sleep(POLL_INTERVAL)
    
    except Exception as e:
        logger.error(f"Error in generate: {e}")
        await progress_msg.edit_text(f"❌ Terjadi kesalahan: {str(e)}")

# Callback untuk tombol Generate Lagi
@dp.callback_query_handler(lambda c: c.data == 'new_generate')
async def regenerate_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await start_generate(callback_query.message)

# Handler untuk semua pesan yang bukan command
@dp.message_handler()
async def default_handler(msg: types.Message):
    # Cek apakah pesan berisi kata kunci generate
    text = msg.text.lower()
    if "gambar" in text or "generate" in text or "buat" in text:
        await start_generate(msg)
    else:
        # Saran untuk menggunakan commands
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("🎨 Generate Gambar", callback_data="new_generate"),
            InlineKeyboardButton("📝 Perbaiki Prompt", callback_data="explain_textgen")
        )
        await msg.reply(
            "Gunakan perintah berikut:\n\n"
            "`/generate` - untuk membuat gambar\n"
            "`/textgen <prompt>` - untuk memperbaiki prompt\n"
            "`/usage` - cek sisa kuota harian kamu", 
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

# Callback untuk tombol Perbaiki Prompt
@dp.callback_query_handler(lambda c: c.data == 'explain_textgen')
async def explain_textgen(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await bot.send_message(
        callback_query.from_user.id,
        "Untuk memperbaiki prompt, gunakan perintah:\n\n"
        "`/textgen <deskripsi gambar kamu>`\n\n"
        "Contoh:\n"
        "`/textgen kucing di bawah pohon sakura`",
        parse_mode="Markdown"
    )

# Error handler global
@dp.errors_handler()
async def error_handler(update, exception):
    logger.exception(f"Update: {update}, error: {exception}")
    return True

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
