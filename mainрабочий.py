import os
import json
import io
import asyncio
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from huggingface_hub import InferenceClient
import speech_recognition as sr
from pydub import AudioSegment
from PIL import Image

# ==========================================
# ⚙️ КОНФИГУРАЦИЯ
# ==========================================
class Config:
    TELEGRAM_TOKEN = "8430174501:AAFt_GVWex1qWmBMmqa1EDDhcZBo9pBcj14"
    HF_TOKEN = "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"
    OWNER_ID = 8138124186  
    
    MODEL_TEXT = "Qwen/Qwen2.5-7B-Instruct"
    MODEL_IMG = "stabilityai/stable-diffusion-xl-base-1.0"
    
    DATA_DIR = "bot_data"
    FILES = {
        "users": f"{DATA_DIR}/users.json",
        "memory": f"{DATA_DIR}/memory.json",
        "sessions": f"{DATA_DIR}/sessions.json",
        "banned": f"{DATA_DIR}/banned.json"
    }

if not os.path.exists(Config.DATA_DIR):
    os.makedirs(Config.DATA_DIR)

# ==========================================
# 💾 МЕНЕДЖЕР ДАННЫХ
# ==========================================
class Database:
    @staticmethod
    def load(filepath, default_val):
        if not os.path.exists(filepath): return default_val
        try:
            with open(filepath, "r", encoding="utf-8") as f: return json.load(f)
        except: return default_val

    @staticmethod
    def save(filepath, data):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

# Загрузка БД
users_db = Database.load(Config.FILES["users"], {})
memory_db = Database.load(Config.FILES["memory"], {})
sessions_db = Database.load(Config.FILES["sessions"], {})
banned_db = Database.load(Config.FILES["banned"], [])

# ==========================================
# 🧠 ИНТЕЛЛЕКТ И ГРАФИКА
# ==========================================
client = InferenceClient(token=Config.HF_TOKEN)
recognizer = sr.Recognizer()

async def get_ai_response(uid, text, role_instruction=None):
    # Достаем память о пользователе
    user_memory = memory_db.get(str(uid), "Информация отсутствует")
    
    system_prompt = (
        f"Ты — ИИ-ассистент, созданный @g0npo. "
        f"Твоя текущая роль: {role_instruction if role_instruction else 'Универсальный помощник'}. "
        f"Твоя память о пользователе: {user_memory}. Используй эти факты в общении."
    )
    
    try:
        response = ""
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": text}]
        stream = client.chat_completion(model=Config.MODEL_TEXT, messages=messages, max_tokens=1000, stream=True)
        for chunk in stream:
            content = chunk.choices[0].delta.content
            if content: response += content
        return response.strip()
    except: return "⚠️ Ошибка связи с мозгом."

async def generate_image(prompt):
    try:
        # Генерация через Hugging Face API
        image = client.text_to_image(prompt, model=Config.MODEL_IMG)
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        return img_byte_arr
    except Exception as e:
        print(f"IMG Error: {e}")
        return None

# ==========================================
# 🎮 ОСНОВНЫЕ ФУНКЦИИ
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in users_db:
        users_db[uid] = {"date": datetime.now().strftime("%Y-%m-%d"), "name": update.effective_user.first_name}
        Database.save(Config.FILES["users"], users_db)
    
    kb = [['🎓 Учеба', '🚗 Авто'], ['💻 IT', '🍳 Кухня'], ['🧠 Моя Память', '🆘 Помощь']]
    await update.message.reply_text(
        f"🚀 Привет, {update.effective_user.first_name}!\nЯ — ИИ бот от @g0npo.\n\n"
        "Пиши текст, шли голосовые или используй `/img [описание]` для рисования!",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if int(uid) in banned_db: return
    text = update.message.text

    # Обработка выбора темы
    topics = {'🎓 Учеба': 'Учитель', '🚗 Авто': 'Механик', '💻 IT': 'Программист', '🍳 Кухня': 'Шеф-повар'}
    if text in topics:
        sessions_db[uid] = topics[text]
        Database.save(Config.FILES["sessions"], sessions_db)
        await update.message.reply_text(f"✅ Режим изменен на: {topics[text]}")
        return

    # Просмотр памяти
    if text == '🧠 Моя Память':
        mem = memory_db.get(uid, "Я еще ничего не запомнил о тебе.")
        await update.message.reply_text(f"📝 **Вот что я о тебе знаю:**\n\n{mem}", parse_mode='Markdown')
        return

    # Запись в память (команда "запомни...")
    if text.lower().startswith("запомни"):
        new_fact = text[7:].strip()
        old_mem = memory_db.get(uid, "")
        memory_db[uid] = f"{old_mem} | {new_fact}".strip(" | ")
        Database.save(Config.FILES["memory"], memory_db)
        await update.message.reply_text("✍️ Записал в память!")
        return

    # Обычный ответ ИИ
    wait_msg = await update.message.reply_text("💭")
    res = await get_ai_response(uid, text, sessions_db.get(uid))
    await context.bot.edit_message_text(res, chat_id=update.effective_chat.id, message_id=wait_msg.message_id)

async def handle_img_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Напиши: `/img котик в космосе`", parse_mode='Markdown')
        return
    
    prompt = " ".join(context.args)
    wait_msg = await update.message.reply_text("🎨 Рисую... (это займет 10-15 сек)")
    
    photo = await generate_image(prompt)
    if photo:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption=f"🖼 По запросу: {prompt}")
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=wait_msg.message_id)
    else:
        await context.bot.edit_message_text("⚠️ Не удалось создать картинку.", chat_id=update.effective_chat.id, message_id=wait_msg.message_id)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    wait_msg = await update.message.reply_text("🎤 Слушаю...")
    
    temp_ogg = f"v_{uid}.ogg"
    temp_wav = f"v_{uid}.wav"
    
    try:
        file = await context.bot.get_file(update.message.voice.file_id)
        await file.download_to_drive(temp_ogg)
        
        # Конвертация
        AudioSegment.from_file(temp_ogg).export(temp_wav, format="wav")
        
        with sr.AudioFile(temp_wav) as source:
            audio = recognizer.record(source)
            text = recognizer.recognize_google(audio, language="ru-RU")
        
        response = await get_ai_response(uid, text, sessions_db.get(uid))
        await context.bot.edit_message_text(f"🗣 _{text}_\n\n{response}", chat_id=update.effective_chat.id, message_id=wait_msg.message_id, parse_mode='Markdown')
        
    except:
        await context.bot.edit_message_text("⚠️ Не удалось распознать голос.", chat_id=update.effective_chat.id, message_id=wait_msg.message_id)
    
    finally:
        for f in [temp_ogg, temp_wav]:
            if os.path.exists(f): os.remove(f)

# ==========================================
# 🚀 ЗАПУСК
# ==========================================
if __name__ == '__main__':
    app = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("img", handle_img_cmd))
    app.add_handler(CommandHandler("admin", lambda u,c: u.message.reply_text("🛠 Панель: `/broadcast`, `/ban ID`")))
    
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🔥 БОТ ЗАПУЩЕН!")
    app.run_polling()