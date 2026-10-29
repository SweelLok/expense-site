"""
UKF Mail Bot — телеграм-бот для университетской почты UKF.

Почта: сервер studentmail.ukf.sk (POP3). POP3 видит только «Входящие» —
Спам и Корзина недоступны (ограничение протокола сервера UKF).

Возможности:
  • автопроверка новых писем (с вложениями);
  • /check — проверить почту сейчас;
  • /getmail — выгрузка писем: выбор количества и формата (TXT или ZIP);
  • /search — поиск письма по ключевому слову (везде / отправитель / тема / текст);
  • меню из кнопок Telegram — всё то же без команд.
"""

import asyncio
import html
import io
import logging
import os
import re
import zipfile
from datetime import datetime

from dotenv import load_dotenv
from telegram import (
    Update,
    InputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ConversationHandler,
)

from mail_client import MailClient
from seen_store import SeenStore

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MAIL_USER = os.getenv("MAIL_USER", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# На Fly.io (и любом хостинге с эфемерной ФС) секреты приходят через
# переменные окружения (fly secrets set), а постоянные данные —
# на смонтированный том DATA_DIR (по умолчанию /data).
DATA_DIR = os.environ.get("DATA_DIR")
if DATA_DIR:
    DATA_DIR = os.path.abspath(DATA_DIR)
    os.makedirs(DATA_DIR, exist_ok=True)

# Постоянное хранилище: seen.json, exports, chat_id, логи.
STORE_DIR = DATA_DIR or BASE_DIR
os.makedirs(os.path.join(STORE_DIR, "logs"), exist_ok=True)
os.makedirs(os.path.join(STORE_DIR, "exports"), exist_ok=True)

EXPORTS_DIR = os.path.join(STORE_DIR, "exports")

# chat_id: из переменной окружения (fly secrets), из файла на томе,
# или локально из .env (подставится после /start).
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
_chat_id_file = os.path.join(STORE_DIR, "chat_id")
if not CHAT_ID and os.path.exists(_chat_id_file):
    with open(_chat_id_file, "r", encoding="utf-8") as _f:
        CHAT_ID = _f.read().strip()

CHECK_INTERVAL_MINUTES = 10
HEARTBEAT_INTERVAL_HOURS = 24

# Доступ ограничен владельцем бота по Telegram user_id.
# Узнать свой ID: написать боту @userinfobot в Telegram — он пришлёт число.
# Как только ID известен, впиши его сюда (и/или в .env / fly secrets
# как TELEGRAM_ADMIN_ID — переменная окружения имеет приоритет).
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID", "1084411025").strip()

# Лимит Telegram на файл от бота — 50 МБ. Крупнее не отправляем.
TG_FILE_LIMIT = 49 * 1024 * 1024

# Сколько найденных писем показывать в чат (остальные — в файле).
SEARCH_INLINE_LIMIT = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(STORE_DIR, "logs", "bot.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("ukf-bot")

seen = SeenStore()


def _is_admin(update: Update) -> bool:
    """True, если команду прислал владелец бота."""
    if not ADMIN_ID:
        return True
    user = update.effective_user
    return bool(user) and str(user.id) == str(ADMIN_ID)


BOSS_REPLY = "🛑 Ты не мой босс — и отвечать тебе я не хочу."


# ─────────────────────────── меню (кнопки) ───────────────────────────

BTN_CHECK = "📬 Проверить почту"
BTN_GETMAIL = "📤 Выгрузить письма"
BTN_SEARCH = "🔍 Поиск"
BTN_STATUS = "📊 Статус"
BTN_CANCEL = "❌ Отмена"

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_CHECK), KeyboardButton(BTN_GETMAIL)],
        [KeyboardButton(BTN_SEARCH), KeyboardButton(BTN_STATUS)],
    ],
    resize_keyboard=True,
)

ADMIN_HINT = (
    "Я понимаю команды и кнопки меню:\n"
    "/start — что я умею\n"
    "/check — проверить почту сейчас\n"
    "/getmail — выгрузить письма (выбор количества и формата)\n"
    "/search — найти письмо по ключевому слову\n"
    "/status — состояние бота"
)


# ─────────────────────────── форматирование ───────────────────────────

def _fmt_message(m: dict) -> str:
    # Текст письма может содержать <, >, & — экранируем, иначе
    # Telegram отвергает сообщение как некорректный HTML.
    esc = html.escape
    body = m["body"]
    if len(body) > 3000:
        body = body[:3000] + "…"
    atts = m.get("attachments") or []
    att_line = ""
    if atts:
        names = ", ".join(esc(a["filename"]) for a in atts[:5])
        if len(atts) > 5:
            names += f" и ещё {len(atts) - 5}"
        att_line = f"\n📎 Вложения ({len(atts)}): {names}"
    return (
        f"📧 <b>Новое письмо</b>\n"
        f"👤 От: {esc(str(m['from']))}\n"
        f"📌 Тема: {esc(str(m['subject']))}\n"
        f"🕐 Дата: {esc(str(m['date']))}\n"
        f"📁 Папка: {esc(str(m['folder']))}\n"
        f"{att_line}\n\n"
        f"{esc(body)}"
    )


def _safe_filename(name: str, limit: int = 60) -> str:
    """Приводит тему письма к безопасному имени файла."""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(name)).strip(" .")
    name = name[:limit].strip(" .")
    return name or "письмо"


def _mail_to_txt(m: dict) -> str:
    atts = m.get("attachments") or []
    lines = [
        f"От:     {m['from']}",
        f"Тема:   {m['subject']}",
        f"Дата:   {m['date']}",
        f"Папка:  {m['folder']}",
    ]
    if atts:
        lines.append(f"Вложения ({len(atts)}): " + ", ".join(a["filename"] for a in atts))
    lines.append("-" * 70)
    lines.append(m["body"] or "(пустое письмо)")
    return "\n".join(lines)


async def _send_attachments(message, attachments: list[dict]) -> None:
    """Присылает вложения письма документами (ответом на сообщение)."""
    for att in attachments:
        if att["size"] > TG_FILE_LIMIT:
            await message.reply_text(
                f"⚠️ Вложение «{att['filename']}» слишком большое "
                f"({att['size'] // 1024 // 1024} МБ) — Telegram не принимает."
            )
            continue
        try:
            await message.reply_document(
                document=InputFile(io.BytesIO(att["data"]), filename=att["filename"])
            )
        except Exception:
            log.exception("Не удалось отправить вложение %s", att["filename"])


# ─────────────────────────── работа с почтой ───────────────────────────

def _scan_inbox() -> list[dict]:
    """Возвращает новые письма из Входящих. При первом запуске только
    запоминает уже существующие письма (чтобы не присылать всю историю)."""
    client = MailClient(MAIL_USER, MAIL_PASSWORD)
    client.connect()
    try:
        messages = client.fetch_messages(limit=100)
        if seen.is_first_run("INBOX"):
            # baseline: старые письма не присылаем
            seen.mark_many(messages)
            seen.save()
            return []
        return [m for m in messages if seen.is_new("INBOX", m["uid"])]
    finally:
        client.disconnect()


def _fetch_all_mail(limit: int = 0) -> list[dict]:
    """Читает письма для выгрузки. limit=0 — все письма."""
    client = MailClient(MAIL_USER, MAIL_PASSWORD)
    client.connect()
    try:
        return client.fetch_all(limit=limit)
    finally:
        client.disconnect()


def _search_mail(keyword: str, field: str) -> list[dict]:
    """Ищет письма по ключевому слову во всех письмах Входящих."""
    messages = _fetch_all_mail(limit=0)
    kw = keyword.lower()
    if field == "from":
        return [m for m in messages if kw in str(m["from"]).lower()]
    if field == "subject":
        return [m for m in messages if kw in str(m["subject"]).lower()]
    if field == "body":
        return [m for m in messages if kw in str(m["body"]).lower()]
    return [
        m
        for m in messages
        if kw in f"{m['from']} {m['subject']} {m['body']}".lower()
    ]


async def send_new_messages(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка почты: рассылает только новые письма. Если писем нет —
    молча выходит, чтобы не засорять чат."""
    if not CHAT_ID:
        return
    try:
        new = await asyncio.to_thread(_scan_inbox)
    except Exception as e:
        log.exception("Ошибка при проверке почты")
        await context.bot.send_message(chat_id=CHAT_ID, text=f"⚠️ Ошибка доступа к почте: {e}")
        return
    for m in new:
        try:
            msg = await context.bot.send_message(
                chat_id=CHAT_ID, text=_fmt_message(m), parse_mode="HTML"
            )
            await _send_attachments_via_bot(context, m.get("attachments") or [], msg.message_id)
            seen.mark("INBOX", m["uid"])  # помечаем только после успешной отправки
        except Exception:
            log.exception("Не удалось отправить письмо в Telegram")
    if new:
        seen.save()
    # Если новых писем нет — ничего не пишем.


async def _send_attachments_via_bot(context, attachments: list[dict], reply_to: int | None) -> None:
    """Вложения для авто-рассылки (отправка по chat_id, а не ответом)."""
    for att in attachments:
        if att["size"] > TG_FILE_LIMIT:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=f"⚠️ Вложение «{att['filename']}» слишком большое — не отправлено.",
            )
            continue
        try:
            await context.bot.send_document(
                chat_id=CHAT_ID,
                document=InputFile(io.BytesIO(att["data"]), filename=att["filename"]),
                reply_to_message_id=reply_to,
            )
        except Exception:
            log.exception("Не удалось отправить вложение %s", att["filename"])


async def heartbeat(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Раз в сутки пишет, что бот жив."""
    if not CHAT_ID:
        return
    try:
        await asyncio.to_thread(MailClient(MAIL_USER, MAIL_PASSWORD).connect)
        mail_ok = "✅"
    except Exception as e:
        mail_ok = f"❌ ({e})"
    text = (
        "🤖 <b>Бот жив</b>\n\n"
        f"📬 Почта {mail_ok}\n"
        f"⏱ Проверяю почту каждые {CHECK_INTERVAL_MINUTES} мин.\n"
        f"💬 Новые письма приходят только если они есть.\n"
        f"🕐 Сейчас: {datetime.now():%d.%m.%Y %H:%M}"
    )
    try:
        await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")
    except Exception:
        log.exception("Не удалось отправить heartbeat")


# ─────────────────────────── базовые команды ───────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    global CHAT_ID
    if not CHAT_ID:
        CHAT_ID = str(update.effective_chat.id)
        _persist_chat_id(CHAT_ID)
    text = (
        "👋 <b>UKF Mail Bot</b>\n\n"
        "Я слежу за твоей университетской почтой и присылаю новые письма "
        "<b>вместе с вложениями</b>.\n\n"
        f"Автопроверка: каждые {CHECK_INTERVAL_MINUTES} мин.\n"
        "Раз в сутки я пишу, что жив.\n\n"
        "Команды и кнопки меню:\n"
        f"{BTN_CHECK} (/check) — проверить почту сейчас\n"
        f"{BTN_GETMAIL} (/getmail) — выгрузка: сколько писем и в каком виде\n"
        f"{BTN_SEARCH} (/search) — поиск письма по слову\n"
        f"{BTN_STATUS} (/status) — состояние бота"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=MAIN_MENU)


def _persist_chat_id(chat_id: str) -> None:
    """Сохраняет chat_id, чтобы переживал перезапуск."""
    if DATA_DIR:
        with open(_chat_id_file, "w", encoding="utf-8") as f:
            f.write(chat_id)
        log.info("chat_id %s сохранён в %s", chat_id, _chat_id_file)
        return
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    key = "TELEGRAM_CHAT_ID"
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={chat_id}\n"
            break
    else:
        lines.append(f"{key}={chat_id}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    log.info("chat_id %s сохранён в .env", chat_id)


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    global CHAT_ID
    if not CHAT_ID:
        CHAT_ID = str(update.effective_chat.id)
        _persist_chat_id(CHAT_ID)
    await update.message.reply_text("🔍 Проверяю почту…")
    try:
        new = await asyncio.to_thread(_scan_inbox)
    except Exception as e:
        log.exception("Ошибка при проверке почты")
        await update.message.reply_text(f"⚠️ Не смог получить доступ к почте: {e}")
        return
    if not new:
        await update.message.reply_text("📭 Новых писем нет.")
        return
    for m in new:
        try:
            msg = await update.message.reply_text(_fmt_message(m), parse_mode="HTML")
            await _send_attachments(msg, m.get("attachments") or [])
            seen.mark("INBOX", m["uid"])
        except Exception:
            log.exception("Не удалось отправить письмо в Telegram")
    seen.save()
    await update.message.reply_text(f"✅ Проверка завершена, новых писем: {len(new)}.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    try:
        await asyncio.to_thread(MailClient(MAIL_USER, MAIL_PASSWORD).connect)
        mail_ok = "✅ подключение к почте работает"
    except Exception as e:
        mail_ok = f"❌ почта недоступна: {e}"
    text = (
        "📊 <b>Статус бота</b>\n\n"
        f"📬 {mail_ok}\n"
        f"👤 Почта: {MAIL_USER}\n"
        f"⏱ Автопроверка: каждые {CHECK_INTERVAL_MINUTES} мин.\n"
        f"💓 Heartbeat: раз в {HEARTBEAT_INTERVAL_HOURS} ч.\n"
        f"🔐 Доступ: только твой user_id ({ADMIN_ID or 'все'})"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ─────────────────────── выгрузка писем (/getmail) ───────────────────────

# Состояния диалогов
SEL_COUNT, SEL_FORMAT, SEL_FIELD, ASK_KEYWORD = range(4)

COUNT_CHOICES = [
    ("10", "10"),
    ("25", "25"),
    ("50", "50"),
    ("100", "100"),
    ("500", "500"),
    ("Все письма", "0"),
]


def _count_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for label, value in COUNT_CHOICES:
        row.append(InlineKeyboardButton(label, callback_data=f"gm:count:{value}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(BTN_CANCEL, callback_data="gm:cancel")])
    return InlineKeyboardMarkup(rows)


def _format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📄 Один общий TXT", callback_data="gm:fmt:txt")],
            [InlineKeyboardButton("🗂 ZIP — файл на каждое письмо", callback_data="gm:fmt:zip")],
            [InlineKeyboardButton(BTN_CANCEL, callback_data="gm:cancel")],
        ]
    )


async def cmd_getmail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_admin(update):
        return ConversationHandler.END
    # Быстрый режим: /getmail 50 zip или /getmail 100 txt
    args = context.args or []
    if len(args) >= 2:
        count_raw, fmt_raw = args[0].lower(), args[1].lower()
        if fmt_raw not in ("txt", "zip"):
            await update.message.reply_text(
                "Формат должен быть txt или zip. Пример: /getmail 50 zip"
            )
            return ConversationHandler.END
        count = 0 if count_raw in ("all", "все", "0") else int(count_raw) if count_raw.isdigit() else None
        if count is None:
            await update.message.reply_text(
                "Количество — число, all или 0 (все). Пример: /getmail 500 zip"
            )
            return ConversationHandler.END
        await _do_getmail(update, context, count, fmt_raw)
        return ConversationHandler.END
    await update.message.reply_text(
        "📤 <b>Выгрузка писем</b>\n\nСколько писем выгрузить? "
        "(если на почте меньше — пришлю все, что есть)",
        parse_mode="HTML",
        reply_markup=_count_keyboard(),
    )
    return SEL_COUNT


async def gm_count_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "gm:cancel":
        await query.edit_message_text("❌ Выгрузка отменена.")
        return ConversationHandler.END
    count = int(query.data.split(":")[-1])
    context.user_data["gm_count"] = count
    label = "все письма" if count == 0 else str(count)
    await query.edit_message_text(
        f"📤 Выгружаю {label}. Теперь выбери формат:",
        reply_markup=_format_keyboard(),
    )
    return SEL_FORMAT


async def gm_fmt_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "gm:cancel":
        await query.edit_message_text("❌ Выгрузка отменена.")
        return ConversationHandler.END
    fmt = query.data.split(":")[-1]
    count = context.user_data.get("gm_count", 0)
    await _do_getmail_cb(query, context, count, fmt)
    return ConversationHandler.END


async def _do_getmail(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int, fmt: str) -> None:
    msg = await update.message.reply_text("📥 Читаю письма с почты, подожди немного…")
    try:
        messages = await asyncio.to_thread(_fetch_all_mail, count)
    except Exception as e:
        log.exception("Ошибка выгрузки почты")
        await msg.edit_text(f"⚠️ Не смог получить доступ к почте: {e}")
        return
    if not messages:
        await msg.edit_text("📭 На почте нет писем.")
        return
    if fmt == "zip":
        await _send_zip(msg, messages)
    else:
        await _send_txt(msg, messages)


async def _do_getmail_cb(query, context: ContextTypes.DEFAULT_TYPE, count: int, fmt: str) -> None:
    await query.edit_message_text("📥 Читаю письма с почты, подожди немного…")
    try:
        messages = await asyncio.to_thread(_fetch_all_mail, count)
    except Exception as e:
        log.exception("Ошибка выгрузки почты")
        await query.edit_message_text(f"⚠️ Не смог получить доступ к почте: {e}")
        return
    if not messages:
        await query.edit_message_text("📭 На почте нет писем.")
        return
    # query.message — сообщение бота; документ пришлём в тот же чат
    if fmt == "zip":
        await _send_zip(query.message, messages)
    else:
        await _send_txt(query.message, messages)


async def _send_txt(message, messages: list[dict]) -> None:
    filename = f"ukf_mail_{datetime.now():%Y%m%d_%H%M}.txt"
    path = os.path.join(EXPORTS_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("Выгрузка писем UKF\n")
        f.write(f"Сгенерировано: {datetime.now():%d.%m.%Y %H:%M}\n")
        f.write(f"Всего писем: {len(messages)}\n")
        f.write("=" * 70 + "\n\n")
        for m in messages:
            f.write(_mail_to_txt(m))
            f.write("\n" + "=" * 70 + "\n\n")
    with open(path, "rb") as f:
        await message.chat.send_document(
            document=InputFile(f, filename=filename),
            caption=f"📄 Письма одним файлом ({len(messages)} шт.)",
        )


async def _send_zip(message, messages: list[dict]) -> None:
    """ZIP: под каждое письмо — свой TXT с названием по теме,
    плюс файлы вложений (если есть)."""
    filename = f"ukf_mail_{datetime.now():%Y%m%d_%H%M}.zip"
    path = os.path.join(EXPORTS_DIR, filename)
    used: set[str] = set()

    def unique(name: str) -> str:
        base, ext = os.path.splitext(name)
        candidate, n = name, 2
        while candidate.lower() in used:
            candidate = f"{base}_{n}{ext}"
            n += 1
        used.add(candidate.lower())
        return candidate

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, m in enumerate(messages, 1):
            base = unique(f"{i:03d}_{_safe_filename(m['subject'])}")
            zf.writestr(f"{base}.txt", _mail_to_txt(m))
            for j, att in enumerate(m.get("attachments") or [], 1):
                if att["size"] > TG_FILE_LIMIT:
                    continue
                att_name = unique(f"{base}__вложение{j}_{_safe_filename(att['filename'], 50)}")
                zf.writestr(att_name, att["data"])
    with open(path, "rb") as f:
        await message.chat.send_document(
            document=InputFile(f, filename=filename),
            caption=f"🗂 Архив: файл на каждое письмо ({len(messages)} шт.)",
        )


# ─────────────────────── поиск писем (/search) ───────────────────────

SEARCH_FIELDS = [
    ("Везде", "all"),
    ("👤 Отправитель", "from"),
    ("📌 Тема", "subject"),
    ("📝 Текст письма", "body"),
]


def _field_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for label, value in SEARCH_FIELDS:
        rows.append([InlineKeyboardButton(label, callback_data=f"s:field:{value}")])
    rows.append([InlineKeyboardButton(BTN_CANCEL, callback_data="s:cancel")])
    return InlineKeyboardMarkup(rows)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_admin(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "🔍 <b>Поиск писем</b>\n\nГде искать?",
        parse_mode="HTML",
        reply_markup=_field_keyboard(),
    )
    return SEL_FIELD


async def s_field_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "s:cancel":
        await query.edit_message_text("❌ Поиск отменён.")
        return ConversationHandler.END
    field = query.data.split(":")[-1]
    context.user_data["s_field"] = field
    field_label = dict(SEARCH_FIELDS).get(field, "везде")
    await query.edit_message_text(
        f"🔍 Ищу в: <b>{field_label}</b>.\n\nПришли ключевое слово (или фразу):",
        parse_mode="HTML",
    )
    return ASK_KEYWORD


async def s_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_admin(update):
        return ConversationHandler.END
    keyword = update.message.text.strip()
    field = context.user_data.get("s_field", "all")
    if not keyword:
        await update.message.reply_text("Ключевое слово пустое — попробуй ещё раз.")
        return ASK_KEYWORD
    status = await update.message.reply_text(f"🔍 Ищу «{keyword}»…")
    try:
        matches = await asyncio.to_thread(_search_mail, keyword, field)
    except Exception as e:
        log.exception("Ошибка поиска")
        await status.edit_text(f"⚠️ Не смог получить доступ к почте: {e}")
        return ConversationHandler.END
    if not matches:
        await status.edit_text(f"📭 Писем по запросу «{keyword}» не найдено.")
        return ConversationHandler.END
    await status.edit_text(
        f"✅ Найдено писем: <b>{len(matches)}</b>. Показываю первые "
        f"{min(len(matches), SEARCH_INLINE_LIMIT)}.",
        parse_mode="HTML",
    )
    for m in matches[:SEARCH_INLINE_LIMIT]:
        try:
            msg = await update.message.reply_text(_fmt_message(m), parse_mode="HTML")
            await _send_attachments(msg, m.get("attachments") or [])
        except Exception:
            log.exception("Не удалось отправить найденное письмо")
    if len(matches) > SEARCH_INLINE_LIMIT:
        # остальные совпадения — файлом
        await _send_txt(
            update.message,
            matches[SEARCH_INLINE_LIMIT:],
        )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Отменено.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ─────────────────────── стражник и роутинг ───────────────────────

async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перехватывает любые сообщения не от владельца."""
    if _is_admin(update):
        return
    user = update.effective_user
    log.info(
        "Чужой пользователь user_id=%s username=%s — отказываю",
        getattr(user, "id", "?"),
        getattr(user, "username", "?"),
    )
    message = update.effective_message
    if message is not None:
        try:
            await message.reply_text(BOSS_REPLY)
        except Exception:
            log.exception("Не удалось отправить отказ чужому пользователю")
    raise ApplicationHandlerStop  # дальше по хендлерам не идём


async def guard_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """То же для нажатий на инлайн-кнопки."""
    if _is_admin(update):
        return
    query = update.callback_query
    if query is not None:
        try:
            await query.answer(BOSS_REPLY, show_alert=True)
        except Exception:
            pass
    raise ApplicationHandlerStop


async def cmd_echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Простой текст: кнопки меню или подсказка команд."""
    text = (update.message.text or "").strip()
    if text == BTN_CHECK:
        await cmd_check(update, context)
    elif text == BTN_STATUS:
        await cmd_status(update, context)
    elif text in (BTN_GETMAIL, BTN_SEARCH):
        # эти запускают диалог — но если сюда попали, значит диалог
        # уже активен и текст — часть ввода (ключевое слово и т.п.)
        await update.message.reply_text(ADMIN_HINT, reply_markup=MAIN_MENU)
    else:
        await update.message.reply_text(ADMIN_HINT, reply_markup=MAIN_MENU)


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан в .env")
    app = Application.builder().token(BOT_TOKEN).build()

    # Стражник: чужим — отказ и обрыв цепочки (в т.ч. для инлайн-кнопок).
    app.add_handler(MessageHandler(filters.ALL, guard), group=-1)
    app.add_handler(CallbackQueryHandler(guard_cb), group=-1)

    # Диалоги: выгрузка и поиск.
    getmail_conv = ConversationHandler(
        entry_points=[
            CommandHandler("getmail", cmd_getmail),
            MessageHandler(filters.Regex(f"^{re.escape(BTN_GETMAIL)}$"), cmd_getmail),
        ],
        states={
            SEL_COUNT: [CallbackQueryHandler(gm_count_cb, pattern="^gm:count:")],
            SEL_FORMAT: [CallbackQueryHandler(gm_fmt_cb, pattern="^gm:fmt:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    search_conv = ConversationHandler(
        entry_points=[
            CommandHandler("search", cmd_search),
            MessageHandler(filters.Regex(f"^{re.escape(BTN_SEARCH)}$"), cmd_search),
        ],
        states={
            SEL_FIELD: [CallbackQueryHandler(s_field_cb, pattern="^s:field:")],
            ASK_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, s_keyword)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(getmail_conv)
    app.add_handler(search_conv)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("status", cmd_status))

    # Кнопки меню без диалога + подсказка на любой текст.
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_CHECK)}$"), cmd_check))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_STATUS)}$"), cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_echo))

    job_queue = app.job_queue
    job_queue.run_repeating(send_new_messages, interval=CHECK_INTERVAL_MINUTES * 60, first=10)
    job_queue.run_repeating(
        heartbeat, interval=HEARTBEAT_INTERVAL_HOURS * 3600, first=HEARTBEAT_INTERVAL_HOURS * 3600
    )

    log.info(
        "Бот запущен. Автопроверка каждые %d м., heartbeat каждые %d ч. Доступ: только user_id=%s",
        CHECK_INTERVAL_MINUTES, HEARTBEAT_INTERVAL_HOURS, ADMIN_ID or "все",
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
