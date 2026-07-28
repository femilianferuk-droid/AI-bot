#!/usr/bin/env python3
"""
Telegram-бот с ИИ (aiogram 3 + Anthropic SDK → smartapi.shop).
• История чатов в SQLite
• Coding-агент: ссылка + запрос в одном сообщении
• Переключение между чатами
• Премиум-эмодзи Telegram
• Клонирование через GitPython (не требует внешнего Git)

Запуск:
    pip install aiogram anthropic aiosqlite GitPython
    BOT_TOKEN=... python bot.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional

import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
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
from git import Repo

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

CODE_SYSTEM_PROMPT: str = """Ты coding-агент. Тебе даны файлы проекта.
Твоя задача — изменить ТОЛЬКО то, что просит пользователь.
Не переписывай файлы целиком.

Возвращай изменения строго в формате:

FILE: путь/к/файлу
<<<<<<< ORIGINAL
точные строки из исходника
=======
новые строки
>>>>>>> FIXED

ВАЖНО:
- original — ТОЧНАЯ копия из исходника
- fixed — только изменённый фрагмент
- Если изменений нет — не включай файл
- Не используй маркеры ``` в ответе"""

DB_PATH: str = "bot_data.db"

# ───────────── Coding-агент ─────────────
WORK_DIR: Path = Path("repos")
WORK_DIR.mkdir(exist_ok=True)

TEXT_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".json", ".yml", ".yaml", ".toml", ".md", ".txt", ".env",
    ".sh", ".bash", ".cfg", ".ini", ".xml", ".sql", ".graphql",
    ".rs", ".go", ".java", ".kt", ".swift", ".c", ".cpp", ".h",
    ".rb", ".php", ".pl", ".lua", ".r", ".dart", ".ex", ".exs",
    ".vue", ".svelte", ".astro", ".tf", ".proto", ".gradle",
}
MAX_FILE_SIZE: int = 200_000
MAX_TOTAL_SIZE: int = 2_000_000

GITHUB_URL_RE: re.Pattern = re.compile(
    r"(https?://)?(www\.)?(github|gitlab|bitbucket)\.com/[^\s]+"
)

# Хранилища
user_repos: dict[int, Path] = {}           # user_id -> путь к репо
user_chats: dict[int, dict[str, int]] = {}  # user_id -> {chat_name: chat_id_int}
active_chat: dict[int, str] = {}            # user_id -> chat_name

# ───────────────── Премиум-эмодзи ───────────────────────────────────────────

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
    "geo":         ("6042011682497106307", "📍"),
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
    "repo":        ("6035128606563241721", "📦"),
    "chat_switch": ("5778672437122045013", "🔄"),
    "plus":        ("6032644646587338669", "➕"),
}


def premoji(key: str) -> str:
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


# ────────────────────────── SQLite ──────────────────────────────────────────

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
            chat_name   TEXT DEFAULT 'default',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_user_time "
        "ON messages(user_id, chat_name, created_at DESC)"
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
    user_id: int,
    role: str,
    content: str,
    model: Optional[str],
    chat_name: str = "default",
) -> None:
    await db.execute(
        "INSERT INTO messages (user_id, role, content, model, chat_name) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, role, content, model, chat_name),
    )
    await db.commit()


async def get_history(
    user_id: int,
    limit: int = MAX_HISTORY,
    chat_name: str = "default",
) -> list[dict]:
    async with db.execute(
        "SELECT role, content FROM messages "
        "WHERE user_id = ? AND chat_name = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, chat_name, limit),
    ) as cursor:
        rows = await cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


async def clear_history(user_id: int, chat_name: str = "default") -> None:
    await db.execute(
        "DELETE FROM messages WHERE user_id = ? AND chat_name = ?",
        (user_id, chat_name),
    )
    await db.commit()


async def get_user_chat_names(user_id: int) -> list[str]:
    async with db.execute(
        "SELECT DISTINCT chat_name FROM messages WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    names = [r[0] for r in rows]
    if "default" not in names:
        names.insert(0, "default")
    return names


# ───────────── Функции coding-агента ─────────────

def clone_repo(url: str) -> Path:
    """Клонирует репозиторий через GitPython."""
    repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
    dest = WORK_DIR / repo_name
    if dest.exists():
        shutil.rmtree(dest)
    Repo.clone_from(url, str(dest), depth=1)
    return dest


def scan_repo(repo_path: Path) -> dict[str, str]:
    """Сканирует репу, возвращает {отн_путь: содержимое} для текстовых файлов."""
    files = {}
    total_size = 0
    for fp in repo_path.rglob("*"):
        if fp.is_file() and fp.suffix.lower() in TEXT_EXTENSIONS:
            size = fp.stat().st_size
            if size > MAX_FILE_SIZE:
                continue
            if total_size + size > MAX_TOTAL_SIZE:
                continue
            try:
                content = fp.read_text(encoding="utf-8")
                rel = str(fp.relative_to(repo_path))
                files[rel] = content
                total_size += size
            except Exception:
                pass
    return files


def build_repo_context(files: dict[str, str], query: str) -> str:
    """Собирает контекст для ИИ: дерево + содержимое релевантных файлов."""
    lines = ["=== FILE TREE ==="]
    for p in sorted(files.keys()):
        lines.append(f"  {p}")

    ql = query.lower()
    relevant = {
        p: c for p, c in files.items()
        if ql in p.lower() or ql in c.lower()[:5000]
    }
    if not relevant:
        relevant = dict(list(files.items())[:5])

    lines.append("\n=== FILE CONTENTS ===")
    for p, content in relevant.items():
        numbered = "\n".join(
            f"{i+1:4d}| {line}"
            for i, line in enumerate(content.split("\n"))
        )
        lines.append(f"\n--- {p} ---")
        lines.append(numbered)

    return "\n".join(lines)


PATCH_RE = re.compile(
    r"FILE:\s*(.+?)\n<<<<<<< ORIGINAL\n(.*?)=======\n(.*?)>>>>>>> FIXED",
    re.DOTALL,
)


def parse_patch(response: str) -> list[dict]:
    """Парсит ответ ИИ в список изменений."""
    patches = []
    for m in PATCH_RE.finditer(response):
        patches.append({
            "file": m.group(1).strip(),
            "original": m.group(2).rstrip(),
            "fixed": m.group(3).rstrip(),
        })
    return patches


def apply_patch(repo_path: Path, patches: list[dict]) -> list[Path]:
    """Применяет патчи к файлам, возвращает список изменённых."""
    changed = []
    for p in patches:
        full = repo_path / p["file"]
        if not full.exists():
            continue
        content = full.read_text(encoding="utf-8")
        if p["original"] in content:
            content = content.replace(p["original"], p["fixed"])
            full.write_text(content, encoding="utf-8")
            changed.append(full)
    return changed


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
            [
                KeyboardButton(text="Чаты", icon_custom_emoji_id=EMOJI["chat_switch"][0]),
                KeyboardButton(text="Репозиторий", icon_custom_emoji_id=EMOJI["repo"][0]),
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


# ───────────────────── Анимация ─────────────────────────────────────────────

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


# ───────────── Вспомогательная: определение chat_name ─────────────

def get_active_chat(uid: int) -> str:
    return active_chat.get(uid, "default")


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
        f"{premoji('trash')} /clear — очистить историю\n"
        f"{premoji('chat_switch')} /chat — управление чатами\n"
        f"{premoji('code')} /repo URL — загрузить репозиторий\n\n"
        f"Можно кинуть ссылку на GitHub с запросом:\n"
        f"<code>https://github.com/... почини баг</code>",
        reply_markup=main_keyboard(),
    )


# ──────── Управление чатами ────────

@dp.message(Command("chat"))
async def cmd_chat(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    args = message.text.split()
    active = get_active_chat(uid)

    if len(args) == 1:
        names = await get_user_chat_names(uid)
        lines = [f"{premoji('chat_switch')} <b>Мои чаты:</b>\n"]
        for n in names:
            mark = f" {premoji('check')}" if n == active else ""
            lines.append(f"  • <b>{n}</b>{mark}")
        lines.append(f"\n{premoji('plus')} <code>/chat new ИМЯ</code> — создать")
        lines.append(f"<code>/chat switch ИМЯ</code> — переключить")
        await message.answer("\n".join(lines))
    elif len(args) >= 2:
        sub = args[1].lower()
        name = args[2] if len(args) >= 3 else None
        if sub == "new" and name:
            active_chat[uid] = name
            await message.answer(
                f"{premoji('plus')} Чат <b>{name}</b> создан и активен."
            )
        elif sub == "switch" and name:
            active_chat[uid] = name
            await message.answer(
                f"{premoji('chat_switch')} Переключено на чат <b>{name}</b>."
            )
        else:
            await message.answer(
                f"{premoji('info')} Формат:\n"
                f"<code>/chat new имя</code>\n"
                f"<code>/chat switch имя</code>"
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
        chat_name = get_active_chat(message.from_user.id)
        await clear_history(message.from_user.id, chat_name)
    await message.answer(
        f"{premoji('trash')} <b>История чата очищена</b>"
    )


@dp.message(Command("history"))
async def cmd_history(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    chat_name = get_active_chat(uid)
    hist = await get_history(uid, limit=10, chat_name=chat_name)
    if not hist:
        await message.answer(f"{premoji('info')} История пуста.")
        return
    lines: list[str] = []
    for m in hist:
        e = premoji("eye") if m["role"] == "user" else premoji("bot")
        lines.append(f"{e} {m['content'][:300]}")
    await message.answer(
        f"{premoji('stats')} <b>Чат: {chat_name}</b>\n\n" + "\n\n".join(lines),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@dp.message(Command("repo"))
async def cmd_repo(message: Message) -> None:
    if not message.from_user:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            f"{premoji('info')} <code>/repo URL</code>"
        )
        return
    url = args[1]
    status = await message.answer(
        f"{premoji('loading')} Клонирую..."
    )
    try:
        repo_path = clone_repo(url)
        user_repos[message.from_user.id] = repo_path
        files = scan_repo(repo_path)
        await status.edit_text(
            f"{premoji('check')} Готово! {len(files)} файлов.\n"
            f"Пиши запрос — исправлю код."
        )
    except Exception as e:
        await status.edit_text(f"{premoji('x')} Ошибка: {e}")


@dp.message(F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer(
        f"{premoji('info')} Неизвестная команда. /help",
    )


# ──────── Reply-кнопки ─────────────────────────────────────────────────────

REPLY_BUTTONS: set[str] = {
    "Модель", "История", "Очистить", "Помощь", "Чаты", "Репозиторий",
}


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
    elif txt == "Чаты":
        await cmd_chat(message)
    elif txt == "Репозиторий":
        await message.answer(
            f"{premoji('info')} Отправь ссылку на GitHub-репозиторий "
            f"с запросом или используй /repo URL"
        )


# ────────────────────── Главный chat-хэндлер ────────────────────────────────

@dp.message(F.text)
async def handle_chat(message: Message, bot: Bot) -> None:
    if not message.from_user or not message.text:
        return

    user = message.from_user
    text = message.text
    uid = user.id
    chat_name = get_active_chat(uid)

    # ── Проверка: GitHub/GitLab/Bitbucket ссылка в тексте? ──
    url_match = GITHUB_URL_RE.search(text)
    if url_match:
        url = url_match.group(0)
        query = text.replace(url, "").strip()

        status = await message.answer(
            f"{premoji('loading')} Клонирую репозиторий..."
        )
        try:
            repo_path = clone_repo(url)
            user_repos[uid] = repo_path
            files = scan_repo(repo_path)

            if not files:
                await status.edit_text(
                    f"{premoji('x')} Нет текстовых файлов."
                )
                return

            if not query:
                await status.edit_text(
                    f"{premoji('check')} Готово! {len(files)} файлов.\n"
                    f"Напиши, что исправить."
                )
                return

            await status.edit_text(
                f"{premoji('loading')} <b>Анализирую код...</b>"
            )

            context = build_repo_context(files, query)

            stop = asyncio.Event()
            anim_task = asyncio.create_task(
                typing_anim(bot, message.chat.id, status.message_id, stop)
            )

            error_occurred = False
            try:
                resp = await client.messages.create(
                    model=MODELS["deepseek"],
                    max_tokens=4096,
                    system=CODE_SYSTEM_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"КОНТЕКСТ:\n{context}\n\nЗАПРОС: {query}"
                        ),
                    }],
                )
                answer = "".join(
                    block.text for block in resp.content
                    if getattr(block, "type", "") == "text"
                ) or "…"
            except Exception as exc:
                log.exception("LLM call failed")
                error_occurred = True
                answer = f"Ошибка: {exc}"
            finally:
                stop.set()
                try:
                    await anim_task
                except Exception:
                    pass

            if not error_occurred:
                patches = parse_patch(answer)
                if patches:
                    changed = apply_patch(repo_path, patches)
                    await status.edit_text(
                        f"{premoji('check')} Изменено: {len(patches)} "
                        f"фрагментов в {len(changed)} файлах."
                    )
                    for fp in changed:
                        try:
                            await message.answer_document(
                                document=types.FSInputFile(fp),
                                caption=(
                                    f"{premoji('file')} {fp.name}"
                                ),
                            )
                        except Exception:
                            pass
                else:
                    await status.edit_text(
                        answer[:MAX_TG_LEN] if answer else "Нет изменений."
                    )
            else:
                await status.edit_text(answer[:MAX_TG_LEN])
            return
        except Exception as e:
            await status.edit_text(
                f"{premoji('x')} Ошибка: {e}"
            )
            return

    # ── Режим coding-агента (репо уже загружен) ──
    if uid in user_repos:
        repo_path = user_repos[uid]
        files = scan_repo(repo_path)

        if not files:
            await message.answer(
                f"{premoji('x')} Нет текстовых файлов."
            )
            return

        thinking = await message.answer(
            f"{premoji('loading')} <b>Анализирую код...</b>"
        )
        stop = asyncio.Event()
        anim_task = asyncio.create_task(
            typing_anim(bot, message.chat.id, thinking.message_id, stop)
        )
        await bot.send_chat_action(
            chat_id=message.chat.id, action="typing"
        )

        context = build_repo_context(files, text)

        error_occurred = False
        try:
            resp = await client.messages.create(
                model=MODELS["deepseek"],
                max_tokens=4096,
                system=CODE_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": (
                        f"КОНТЕКСТ:\n{context}\n\nЗАПРОС: {text}"
                    ),
                }],
            )
            answer = "".join(
                block.text for block in resp.content
                if getattr(block, "type", "") == "text"
            ) or "…"
        except Exception as exc:
            log.exception("LLM call failed")
            error_occurred = True
            answer = f"Ошибка: {exc}"
        finally:
            stop.set()
            try:
                await anim_task
            except Exception:
                pass

        if not error_occurred:
            patches = parse_patch(answer)
            if patches:
                changed = apply_patch(repo_path, patches)
                await thinking.edit_text(
                    f"{premoji('check')} Изменено: {len(patches)} "
                    f"фрагментов в {len(changed)} файлах."
                )
                for fp in changed:
                    try:
                        await message.answer_document(
                            document=types.FSInputFile(fp),
                            caption=f"{premoji('file')} {fp.name}",
                        )
                    except Exception:
                        pass
            else:
                await thinking.edit_text(
                    answer[:MAX_TG_LEN] if answer else "Нет изменений."
                )
        else:
            await thinking.edit_text(answer[:MAX_TG_LEN])
        return

    # ── Обычный чат ──
    u = await get_or_create_user(uid, user.username)
    model_key = u["model_key"]
    model_name = MODELS[model_key]

    await save_message(uid, "user", text, model_name, chat_name)

    history = await get_history(uid, MAX_HISTORY, chat_name)

    thinking = await message.answer(
        f"{premoji('loading')} <b>Думаю… 0с</b>",
    )
    stop = asyncio.Event()
    anim_task = asyncio.create_task(
        typing_anim(bot, message.chat.id, thinking.message_id, stop)
    )
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    error_occurred = False
    try:
        resp = await client.messages.create(
            model=model_name,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        answer = "".join(
            block.text for block in resp.content
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

    if not error_occurred:
        await save_message(uid, "assistant", answer, model_name, chat_name)

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
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    log.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        if db:
            await db.close()


if __name__ == "__main__":
    asyncio.run(main())
