import logging
import aiohttp
import openai
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# Konfigurasi token
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
REPLICATE_API_TOKEN = "YOUR_REPLICATE_API_TOKEN"

openai.api_key = OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# /start
@dp.message_handler(commands=["start"])
async def start_handler(msg: types.Message):
    await msg.reply("Selamat datang!\n\n/generate <prompt> - Buat gambar AI\n/textgen <prompt> - Perbaiki prompt")

# /textgen
@dp.message_handler(commands=["textgen"])
async def textgen_handler(msg: types.Message):
    user_prompt = msg.get_args()
    if not user_prompt:
        await msg.reply("Contoh: /textgen kucing lucu di luar angkasa")
        return

    await msg.reply("Memproses prompt...")
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Perbaiki prompt ini agar lebih jelas untuk AI image generator, maksimal 1 kalimat."},
                {"role": "user", "content": user_prompt}
            ]
        )
        improved = res['choices'][0]['message']['content']
        await msg.reply(f"Prompt disempurnakan:\n`{improved.strip()}`", parse_mode="Markdown")
    except Exception as e:
        await msg.reply(f"Error: {e}")

# /generate
@dp.message_handler(commands=["generate"])
async def generate_handler(msg: types.Message):
    prompt = msg.get_args()
    if not prompt:
        await msg.reply("Contoh: /generate kucing bergaya cyberpunk")
        return

    await msg.reply("Sedang membuat gambar...")

    url = "https://api.replicate.com/v1/predictions"
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "version": "a9758cbf0e03a7e926ef5f115cb50910588f94b21e8c967c88d8f4c576f3d9a3",  # SDXL model
        "input": {
            "prompt": prompt
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status != 201:
                await msg.reply("Gagal membuat permintaan ke Replicate.")
                return
            response = await resp.json()
            prediction_url = response["urls"]["get"]

        # polling hasil
        status = "starting"
        while status not in ["succeeded", "failed"]:
            async with session.get(prediction_url, headers=headers) as poll:
                result = await poll.json()
                status = result["status"]
                if status == "succeeded":
                    image_url = result["output"][0]
                    await msg.reply_photo(photo=image_url, caption=f"Gambar untuk:\n`{prompt}`", parse_mode="Markdown")
                    return
                elif status == "failed":
                    await msg.reply("Gagal menghasilkan gambar.")
                    return

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
