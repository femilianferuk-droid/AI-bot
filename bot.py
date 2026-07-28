#!/usr/bin/env python3
"""
Telegram-бот с ИИ (aiogram 3 + Anthropic SDK → smartapi.shop).
История чатов в SQLite (файл bot_data.db).
Премиум-эмодзи Telegram во всех сообщениях и кнопках.

ENV (обязательные):
    BOT_TOKEN — токен Telegram-бота

ENV (опционально):
    SMART_API_KEY  — ключ прокси (по умолчанию вшитый)
    SMART_BASE_URL — базовый URL (по умолчанию https://api.smartapi.shop)

Запуск:
    pip install aiogram anthropic aiosqlite
    BOT_TOKEN=... python bot.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from anthropic import AsyncAnthropic

# ─────────────────────────── Конфигурация ───────────────────────────────────

BOT_TOKEN: str = os.environ["BOT_TOKEN"]

SMART_API_KEY: str = os.environ.get(
    "SMART_API_KEY",
    "sk-smart-3XD55m5XyNjpez1edNzGkuaqvnnXs6qKm1pf5hQqHEA",
)
SMART_BASE_URL: str = os.environ.get("SMART_BASE_URL", "https://api.smartapi.shop")

MODELS: dict[str, str] = {
    "deepseek": "deepseek-V4-flash",
    "minimax": "minimax-m3",
}
DEFAULT_MODEL_KEY: str = "deepseek"
MAX_HISTORY: int = 20
MAX_TOKENS: int = 2048
MAX_TG_LEN: int = 4000

SYSTEM_PROMPT: str = (
    "Ты дружелюбный ассистент. Отвечай по-русски, кратко и по делу. "
    "Если не знаешь ответа — честно так и скажи."
)

DB_PATH: str = "bot_data.db"

# ───────────────── Премиум-эмодзи (id, fallback) ────────────────────────────

EMOJI: dict[str, tuple[str, str]] = {
    "settings":    ("5870982283724328568", "⚙"),
    "profile":     ("5870994129244131212", "👤"),
    "people":      ("5870772616305839506", "👥"),
    "person_chk":  ("5891207662678317861", "👤"),
    "person_x":    ("5893192487324880883", "👤"),
    "file":        ("5870528606328852614", "📁"),
    "smile":       ("5870764288364252592", "🙂"),
    "growth":      ("5870930636742595124", "📊"),
    "stats":       ("5870921681735781843", "📊"),
    "home":        ("5873147866364514353", "🏘"),
    "lock_cl":     ("6037249452824072506", "🔒"),
    "lock_op":     ("6037496202990194718", "🔓"),
    "megaphone":   ("6039422865189638057", "📣"),
    "check":       ("5870633910337015697", "✅"),
    "x":           ("5870657884844462243", "❌"),
    "pencil":      ("5870676941614354370", "🖋"),
    "trash":       ("5870875489362513438", "🗑"),
    "down":        ("5893057118545646106", "📰"),
    "clip":        ("6039451237743595514", "📎"),
    "link":        ("5769289093221454192", "🔗"),
    "info":        ("6028435952299413210", "ℹ"),
    "bot":         ("6030400221232501136", "🤖"),
    "eye":         ("6037397706505195857", "👁"),
    "eye_off":     ("6037243349675544634", "👁"),
    "send":        ("5963103826075456248", "⬆"),
    "download":    ("6039802767931871481", "⬇"),
    "bell":        ("6039486778597970865", "🔔"),
    "gift":        ("6032644646587338669", "🎁"),
    "clock":       ("5983150113483134607", "⏰"),
    "party":       ("6041731551845159060", "🎉"),
    "font":        ("5870801517140775623", "🔗"),
    "write":       ("5870753782874246579", "✍"),
    "media":       ("6035128606563241721", "🖼"),
    "geo":        ("6042011682497106307", "📍"),
    "wallet":      ("5769126056262898415", "👛"),
    "box":         ("5884479287171485878", "📦"),
    "crypto":      ("5260752406890711732", "👾"),
    "calendar":    ("5890937706803894250", "📅"),
    "tag":         ("5886285355279193209", "🏷"),
    "time":        ("5775896410780079073", "🕓"),
    "apps":        ("5778672437122045013", "📦"),
    "brush":       ("6050679691004612757", "🖌"),
    "text":        ("5771851822897566479", "🔡"),
    "resize":      ("5778479949572738874", "↔"),
    "money":       ("5904462880941545555", "🪙"),
    "money_send":  ("5890848474563352982", "🪙"),
    "money_recv":  ("5879814368572478751", "🏧"),
    "code":        ("5940433880585605708", "🔨"),
    "loading":     ("5345906554510012647", "🔄"),
}


def premoji(key: str) -> str:
    """HTML-тег для премиум-эмодзи."""
    eid, fallback = EMOJI[key]
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'


# ──────────────────────────── Логирование ───────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bot")

# ────────────────────────────── Клиенты ─────────────────────────────────────

client: AsyncAnthropic = AsyncAnthropic(
    api_key=SMART_API_KEY,
    base_url=SMART_BASE_URL,
)
db: Optional[aiosqlite.Connection] = None

# ──────────────────────────── Диспетчер ─────────────────────────────────────

dp = Dispatcher()


# ────────────────────────── SQLite (aiosqlite) ──────────────────────────────

async def init_db() -> None:
    global db
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            model_key   TEXT NOT NULL DEFAULT 'deepseek',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            role        TEXT   NOT NULL CHECK (role IN ('user','assistant','system')),
            content     TEXT   NOT NULL,
            model       TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_user_time "
        "ON messages(user_id, created_at DESC)"
    )
    await db.commit()
    log.info("SQLite ready")


async def get_or_create_user(user_id: int, username: Optional[str]) -> dict:
    async with db.execute(
        "SELECT user_id, model_key FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, model_key) "
            "VALUES (?, ?, ?)",
            (user_id, username, DEFAULT_MODEL_KEY),
        )
        await db.commit()
        return {"user_id": user_id, "model_key": DEFAULT_MODEL_KEY}
    return {"user_id": row[0], "model_key": row[1]}


async def set_user_model(user_id: int, model_key: str) -> None:
    await db.execute(
        "UPDATE users SET model_key = ? WHERE user_id = ?",
        (model_key, user_id),
    )
    await db.commit()


async def save_message(
    user_id: int, role: str, content: str, model: Optional[str]
) -> None:
    await db.execute(
        "INSERT INTO messages (user_id, role, content, model) "
        "VALUES (?, ?, ?, ?)",
        (user_id, role, content, model),
    )
    await db.commit()


async def get_history(user_id: int, limit: int = MAX_HISTORY) -> list[dict]:
    async with db.execute(
        "SELECT role, content FROM messages "
        "WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ) as cursor:
        rows = await cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


async def clear_history(user_id: int) -> None:
    await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    await db.commit()


# ───────────────────────────── Клавиатуры ───────────────────────────────────

def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Модель", icon_custom_emoji_id=EMOJI["settings"][0]),
                KeyboardButton(text="История", icon_custom_emoji_id=EMOJI["stats"][0]),
            ],
            [
                KeyboardButton(text="Очистить", icon_custom_emoji_id=EMOJI["trash"][0]),
                KeyboardButton(text="Помощь", icon_custom_emoji_id=EMOJI["info"][0]),
            ],
        ],
        resize_keyboard=True,
    )


def model_keyboard(current: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, name in MODELS.items():
        is_current = key == current
        rows.append([
            InlineKeyboardButton(
                text=name,
                callback_data=f"model:{key}",
                icon_custom_emoji_id=EMOJI["check" if is_current else "x"][0],
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="Закрыть",
            callback_data="close",
            icon_custom_emoji_id=EMOJI["x"][0],
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ───────────────────── Анимация «Думаю… Nс» ─────────────────────────────────

async def typing_anim(
    bot: Bot, chat_id: int, message_id: int, stop: asyncio.Event,
) -> None:
    start = time.monotonic()
    while not stop.is_set():
        elapsed = int(time.monotonic() - start)
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{premoji('loading')} <b>Думаю… {elapsed}с</b>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            continue


# ───────────────────────────── Команды ──────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    if user:
        await get_or_create_user(user.id, user.username)
    await message.answer(
        f"{premoji('bot')} <b>Привет! Я бот с ИИ.</b>\n\n"
        f"{premoji('settings')} /model — выбрать модель\n"
        f"{premoji('stats')} /history — последние сообщения\n"
        f"{premoji('trash')} /clear — очистить историю\n\n"
        f"Просто напиши сообщение — отвечу.",
        reply_markup=main_keyboard(),
    )


@dp.message(Command("model"))
async def cmd_model(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    u = await get_or_create_user(user.id, user.username)
    current = u["model_key"]
    await message.answer(
        f"{premoji('settings')} <b>Выбор модели</b>\n\n"
        f"Текущая: <b>{MODELS[current]}</b>\n"
        f"Жми кнопку, чтобы переключить:",
        reply_markup=model_keyboard(current),
    )


@dp.callback_query(F.data.startswith("model:"))
async def model_callback(callback: CallbackQuery) -> None:
    key = (callback.data or "").split(":", 1)[1]
    if key not in MODELS:
        await callback.answer("Неизвестная модель", show_alert=True)
        return
    if callback.from_user:
        await set_user_model(callback.from_user.id, key)
    name = MODELS[key]
    if callback.message:
        try:
            await callback.message.edit_text(
                f"{premoji('check')} Модель переключена на <b>{name}</b>",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="Закрыть",
                            callback_data="close",
                            icon_custom_emoji_id=EMOJI["x"][0],
                        )
                    ]]
                ),
            )
        except Exception:
            pass
    await callback.answer(f"{premoji('check')} {name}")


@dp.callback_query(F.data == "close")
async def close_callback(callback: CallbackQuery) -> None:
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
    await callback.answer()


@dp.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    if message.from_user:
        await clear_history(message.from_user.id)
    await message.answer(f"{premoji('trash')} <b>История очищена</b>")


@dp.message(Command("history"))
async def cmd_history(message: Message) -> None:
    if not message.from_user:
        return
    hist = await get_history(message.from_user.id, limit=10)
    if not hist:
        await message.answer(f"{premoji('info')} История пуста.")
        return
    lines: list[str] = []
    for m in hist:
        e = premoji("eye") if m["role"] == "user" else premoji("bot")
        lines.append(f"{e} {m['content'][:300]}")
    await message.answer(
        f"{premoji('stats')} <b>Последние сообщения:</b>\n\n" + "\n\n".join(lines),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@dp.message(F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer(
        f"{premoji('info')} Неизвестная команда. Попробуй /help.",
    )


# ──────── Reply-кнопки ─────────────────────────────────────────────────────

REPLY_BUTTONS: set[str] = {"Модель", "История", "Очистить", "Помощь"}


@dp.message(F.text.in_(REPLY_BUTTONS))
async def reply_button_handler(message: Message) -> None:
    txt = message.text or ""
    if txt == "Модель":
        await cmd_model(message)
    elif txt == "История":
        await cmd_history(message)
    elif txt == "Очистить":
        await cmd_clear(message)
    elif txt == "Помощь":
        await cmd_help(message)


# ────────────────────── Главный chat-хэндлер ────────────────────────────────

@dp.message(F.text)
async def handle_chat(message: Message, bot: Bot) -> None:
    if not message.from_user or not message.text:
        return

    user = message.from_user
    text = message.text

    u = await get_or_create_user(user.id, user.username)
    model_key = u["model_key"]
    model_name = MODELS[model_key]

    # Сохраняем вопрос
    await save_message(user.id, "user", text, model_name)

    # Берём историю
    history = await get_history(user.id, MAX_HISTORY)

    # Анимация «Думаю…»
    thinking = await message.answer(
        f"{premoji('loading')} <b>Думаю… 0с</b>",
    )
    stop = asyncio.Event()
    anim_task = asyncio.create_task(
        typing_anim(bot, message.chat.id, thinking.message_id, stop)
    )
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Запрос к модели
    error_occurred = False
    try:
        resp = await client.messages.create(
            model=model_name,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        answer = "".join(
            block.text
            for block in resp.content
            if getattr(block, "type", "") == "text"
        ) or "…"
    except Exception as exc:
        log.exception("LLM call failed")
        error_occurred = True
        answer = f"{premoji('x')} <b>Ошибка модели:</b> {exc}"
    finally:
        stop.set()
        try:
            await anim_task
        except Exception:
            pass

    # Сохраняем ответ
    if not error_occurred:
        await save_message(user.id, "assistant", answer, model_name)

    # Отправляем ответ
    try:
        if len(answer) <= MAX_TG_LEN:
            await thinking.edit_text(answer)
        else:
            await thinking.edit_text(answer[:MAX_TG_LEN])
            for offset in range(MAX_TG_LEN, len(answer), MAX_TG_LEN):
                await message.answer(answer[offset:offset + MAX_TG_LEN])
    except Exception:
        for offset in range(0, len(answer), MAX_TG_LEN):
            await message.answer(answer[offset:offset + MAX_TG_LEN])


# ──────────────────────────────── Запуск ────────────────────────────────────

async def main() -> None:
    await init_db()
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    log.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        if db:
            await db.close()


if __name__ == "__main__":
    asyncio.run(main())
