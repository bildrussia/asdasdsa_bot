import os
import json
import io
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from huggingface_hub import InferenceClient
import speech_recognition as sr
from pydub import AudioSegment

# ==========================================
# ⚙️ КОНФИГУРАЦИЯ
# ==========================================
class Config:
    TELEGRAM_TOKEN = "8430174501:AAFt_GVWex1qWmBMmqa1EDDhcZBo9pBcj14"
    HF_TOKEN = "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"
    OWNER_ID = 8138124186  
    OWNER_LINK = "@g0npo"
    
    MODEL_TEXT = "Qwen/Qwen2.5-7B-Instruct"
    MODEL_IMG = "black-forest-labs/FLUX.1-schnell" 
    
    DATA_DIR = "bot_data"
    FILES = {
        "users": f"{DATA_DIR}/users.json",
        "memory": f"{DATA_DIR}/memory.json",
        "sessions": f"{DATA_DIR}/sessions.json",
        "history": f"{DATA_DIR}/history.json",
        "banned": f"{DATA_DIR}/banned.json",
        "admins": f"{DATA_DIR}/admins.json" 
    }

    # ВЕРНУЛ ВСЕ ЛИЧНОСТИ, УБРАЛ АВТОРСТВО ИЗ ПРOМПТОВ
    MODES = {
       "🤖 Обычный": f"Ты универсальный ИИ. Твой создатель — {OWNER_LINK}. Пиши кратко на русском.",
        "🚗 Механик": f"Ты суровый автомеханик. Твой создатель — {OWNER_LINK}. Используй гаражный сленг.",
        "🎓 Учитель": f"Ты строгий учитель. Твой создатель — {OWNER_LINK}. Объясняй грамотно.",
        "💼 Бизнес": f"Ты акула бизнеса. Твой создатель — {OWNER_LINK}. Говори о профите.",
        "🍳 Кухня": f"Ты шеф-повар. Твой создатель — {OWNER_LINK}. Говори о еде.",
        "💬 Бро": f"Ты лучший друг. Твой создатель — {OWNER_LINK}. Общайся на сленге.",
        "💻 Кодер": f"Ты Senior Developer. Твой создатель — {OWNER_LINK}. Пиши код.",
        "👊 Пацан": f"Ты четкий пацан. Твой создатель — {OWNER_LINK}. Общайся по понятиям.",
        "🧠 Психолог": f"Ты чуткий психолог. Твой создатель — {OWNER_LINK}.",
        "📜 Философ": f"Ты мудрец. Твой создатель — {OWNER_LINK}. Рассуждай о вечном.",
        "🔍 Сыщик": f"Ты детектив. Твой создатель — {OWNER_LINK}. Веди расследование."
    }

if not os.path.exists(Config.DATA_DIR):
    os.makedirs(Config.DATA_DIR)

# ==========================================
# 💾 БАЗА ДАННЫХ
# ==========================================
def load_db(path, default):
    if not os.path.exists(path): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_db(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

users_db = load_db(Config.FILES["users"], {})
memory_db = load_db(Config.FILES["memory"], {})
sessions_db = load_db(Config.FILES["sessions"], {})
history_db = load_db(Config.FILES["history"], {})
banned_db = load_db(Config.FILES["banned"], [])
admins_db = load_db(Config.FILES["admins"], {str(Config.OWNER_ID): {"lvl": 2, "name": "Основатель"}})

client = InferenceClient(token=Config.HF_TOKEN)
recognizer = sr.Recognizer()

# ==========================================
# 🛡 СИСТЕМА УРОВНЕЙ
# ==========================================
def get_lvl(uid):
    uid = str(uid)
    if uid == str(Config.OWNER_ID): return 2
    return admins_db.get(uid, {}).get("lvl", 0)

def update_user_db(user):
    uid = str(user.id)
    users_db[uid] = {
        "name": user.first_name,
        "username": f"@{user.username}" if user.username else "нет",
        "date": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    save_db(Config.FILES["users"], users_db)

# ==========================================
# 🧠 МОЗГИ ИИ
# ==========================================
async def get_ai_response(uid, text):
    uid = str(uid)
    mode = sessions_db.get(uid, "🤖 Обычный")
    system = Config.MODES.get(mode, Config.MODES["🤖 Обычный"])
    mem = memory_db.get(uid, "Нет данных")
    hist = history_db.get(uid, [])[-6:]
    
    messages = [{"role": "system", "content": f"{system}\nПамять о юзере: {mem}\nОТВЕЧАЙ СТРОГО НА РУССКОМ."}]
    for h in hist:
        messages.append({"role": "user" if h['r'] == 'u' else "assistant", "content": h['t']})
    messages.append({"role": "user", "content": text})

    try:
        res = client.chat_completion(model=Config.MODEL_TEXT, messages=messages, max_tokens=1000)
        ans = res.choices[0].message.content
        hist.append({"r": "u", "t": text}); hist.append({"r": "a", "t": ans})
        history_db[uid] = hist[-10:]; save_db(Config.FILES["history"], history_db)
        return ans
    except: return "⚠️ Нейросеть временно недоступна."

# ==========================================
# 🎤 ГОЛОС
# ==========================================
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if int(uid) in banned_db: return
    wait = await update.message.reply_text("🎤 Распознаю...")
    path_ogg, path_wav = f"v_{uid}.ogg", f"v_{uid}.wav"
    try:
        f = await context.bot.get_file(update.message.voice.file_id)
        await f.download_to_drive(path_ogg)
        AudioSegment.from_file(path_ogg).export(path_wav, format="wav")
        with sr.AudioFile(path_wav) as src:
            text = recognizer.recognize_google(recognizer.record(src), language="ru-RU")
        res = await get_ai_response(uid, text)
        await wait.edit_text(f"🗣 <i>{text}</i>\n\n{res}", parse_mode=ParseMode.HTML)
    except: await wait.edit_text("⚠️ Ошибка обработки голоса.")
    finally:
        for f in [path_ogg, path_wav]:
            if os.path.exists(f): os.remove(f)

# ==========================================
# 👑 АДМИНКА
# ==========================================
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lvl = get_lvl(uid)
    if lvl < 1: return
    
    cmd = update.message.text.split()[0][1:] # получаем имя команды без /
    if not context.args and cmd != "list": return
    target = context.args[0] if context.args else ""

    if cmd == "list" and lvl == 2:
        msg = "📊 <b>Список пользователей:</b>\n"
        for k, v in users_db.items():
            msg += f"{'🚫' if int(k) in banned_db else '👤'} <code>{k}</code> | {v['name']}\n"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    
    elif cmd == "ban":
        if get_lvl(target) >= lvl and uid != Config.OWNER_ID:
            await update.message.reply_text("❌ Нет прав на бан этого юзера.")
            return
        if int(target) not in banned_db: banned_db.append(int(target))
        save_db(Config.FILES["banned"], banned_db)
        await update.message.reply_text(f"🔨 ID {target} забанен.")
        
    elif cmd == "unban":
        if int(target) in banned_db: banned_db.remove(int(target))
        save_db(Config.FILES["banned"], banned_db)
        await update.message.reply_text(f"✅ ID {target} разбанен.")

    elif cmd == "promote" and lvl == 2:
        admins_db[target] = {"lvl": 1, "name": users_db.get(target, {}).get("name", "Admin")}
        save_db(Config.FILES["admins"], admins_db)
        await update.message.reply_text(f"⭐ ID {target} теперь Админ.")

    elif cmd == "demote" and lvl == 2:
        if target in admins_db: del admins_db[target]
        save_db(Config.FILES["admins"], admins_db)
        await update.message.reply_text(f"🗑 ID {target} больше не Админ.")

# ==========================================
# 💬 ТЕКСТ И ИНТЕРФЕЙС
# ==========================================
def main_kb(uid):
    btns = [[KeyboardButton("🎭 Личности"), KeyboardButton("👤 Профиль")], [KeyboardButton("🧠 Память"), KeyboardButton("🆘 Помощь")]]
    if get_lvl(uid) >= 1: btns.append([KeyboardButton("👑 Админка")])
    return ReplyKeyboardMarkup(btns, resize_keyboard=True)

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    update_user_db(update.effective_user)
    if int(uid) in banned_db: return
    text = update.message.text

    if text == "🎭 Личности":
        keys = list(Config.MODES.keys())
        # Сетка 2 кнопки в ряд
        kb = [keys[i:i+2] for i in range(0, len(keys), 2)]
        kb = [[KeyboardButton(btn) for btn in row] for row in kb]
        kb.append([KeyboardButton("🔙 Назад")])
        await update.message.reply_text("Выбери роль для ИИ:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return
    
    if text in Config.MODES:
        sessions_db[uid] = text; history_db[uid] = []
        save_db(Config.FILES["sessions"], sessions_db); save_db(Config.FILES["history"], history_db)
        await update.message.reply_text(f"✅ Я сменил личность на: {text}", reply_markup=main_kb(uid))
        return

    if text == "👤 Профиль":
        lvl = get_lvl(uid)
        st = "Юзер" if lvl == 0 else "Админ" if lvl == 1 else "Основатель"
        await update.message.reply_text(f"👤 <b>Профиль</b>\n🆔 ID: <code>{uid}</code>\n👑 Уровень: {st}", parse_mode=ParseMode.HTML)
        return

    if text == "🧠 Память":
        await update.message.reply_text(f"🧠 <b>Я помню:</b>\n{memory_db.get(uid, 'Пусто')}", parse_mode=ParseMode.HTML)
        return

    if text == "🆘 Помощь":
        h = (f"🆘 <b>Помощь:</b>\n\n"
             f"🖼 <code>/img [текст]</code> — нарисовать\n"
             f"✍️ <code>запомни [факт]</code> — сохранить в память\n"
             f"🎤 Отправь голос, чтобы пообщаться\n\n"
             f"👑 Создатель: {Config.OWNER_LINK}")
        await update.message.reply_text(h, parse_mode=ParseMode.HTML)
        return

    if text == "👑 Админка" and get_lvl(uid) >= 1:
        adm = "🛠 <b>Команды:</b>\n/ban ID\n/unban ID\n"
        if get_lvl(uid) == 2: adm += "/list, /promote ID, /demote ID"
        await update.message.reply_text(adm, parse_mode=ParseMode.HTML)
        return

    if text.lower().startswith("запомни "):
        memory_db[uid] = text[8:]
        save_db(Config.FILES["memory"], memory_db)
        await update.message.reply_text("✍️ Запомнил!")
        return

    if text == "🔙 Назад":
        await update.message.reply_text("Главное меню:", reply_markup=main_kb(uid))
        return

    wait = await update.message.reply_text("💭")
    ans = await get_ai_response(uid, text)
    await wait.edit_text(ans)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_db(update.effective_user)
    await update.message.reply_text("🚀 Привет! Я готов к работе.", reply_markup=main_kb(update.effective_user.id))

async def handle_img(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    p = " ".join(context.args); msg = await update.message.reply_text("🎨 Рисую...")
    try:
        tr = client.chat_completion(model=Config.MODEL_TEXT, messages=[{"role":"user","content":f"Translate to English: {p}"}])
        img = client.text_to_image(tr.choices[0].message.content, model=Config.MODEL_IMG)
        bio = io.BytesIO(); img.save(bio, format='PNG'); bio.seek(0)
        await context.bot.send_photo(update.effective_chat.id, bio, caption=f"🖼 {p}"); await msg.delete()
    except: await msg.edit_text("❌ Ошибка генерации.")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Эта команда неверная, её не существует или вы ввели в неправильной форме.")

if __name__ == '__main__':
    app = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("img", handle_img))
    app.add_handler(CommandHandler(["list", "ban", "unban", "promote", "demote"], cmd_admin))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    print("🔥 БОТ ЗАПУЩЕН")
    app.run_polling()