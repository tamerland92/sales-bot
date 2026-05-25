import os
import re
import logging
from typing import Optional
from telegram import Update, InputFile
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

MONTAGE_KEYWORDS = ["выезд специалиста", "20 000 тенге", "щитовая", "маршрут от генератора", "прокладки кабеля", "прокладку кабеля"]

FOLLOWUP_TEXT = (
    "Пожалуйста, оставьте своё имя и номер телефона — "
    "мы свяжемся с вами и предоставим официальное коммерческое предложение, "
    "а также подскажем по наличию."
)


async def _send_followup(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    try:
        await context.bot.send_message(chat_id=chat_id, text=FOLLOWUP_TEXT)
    except Exception as e:
        logger.error(f"Ошибка отправки follow-up: {e}")


def _schedule_followup(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    job_name = f"followup_{chat_id}"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    context.job_queue.run_once(_send_followup, when=60, data=chat_id, name=job_name)


def _cancel_followup(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    job_name = f"followup_{chat_id}"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

ALL_PHOTOS = [
    "photos/canopy.jpg",
    "photos/open.jpg",
    "photos/container.jpg",
]

from database.db import upsert_customer, save_message, get_history, save_order
from services.ai import get_ai_response


def _extract_phone(text: str) -> Optional[str]:
    match = re.search(r'[\+\d][\d\s\-\(\)]{7,}', text)
    if match:
        phone = re.sub(r'[\s\-\(\)]', '', match.group())
        if len(phone) >= 7:
            return phone
    return None


def _already_ordered(history: list) -> bool:
    """Проверяем не была ли уже оформлена заявка в этом диалоге."""
    for msg in history[-10:]:
        if msg.get("role") == "assistant" and "заявка принята" in msg.get("content", "").lower():
            return True
    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = update.message.text

    customer_name = user.full_name or user.username or str(chat_id)

    upsert_customer(chat_id, user.username or "", customer_name)
    logger.info(f"📩 [{customer_name}]: {text}")
    _cancel_followup(context, chat_id)
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    history = get_history(chat_id, limit=20)

    # Если в сообщении есть телефон — сразу оформляем заявку
    phone = _extract_phone(text)
    if phone and not _already_ordered(history):
        # Собираем контекст заказа из истории
        order_context = _build_order_context(history, text, customer_name)

        order_id = save_order(chat_id, customer_name, f"{order_context} | Тел: {phone}")
        save_message(chat_id, "user", text)

        confirm_text = (
            f"✅ Заявка #{order_id} принята!\n\n"
            f"Наш менеджер свяжется с вами по номеру {phone} в ближайшее время."
        )
        save_message(chat_id, "assistant", confirm_text)
        await update.message.reply_text(confirm_text)

        await notify_manager(
            context=context,
            chat_id=chat_id,
            customer_name=customer_name,
            username=user.username,
            details=f"{order_context}\nТелефон: {phone}",
            order_id=order_id,
        )
        return

    # Обычный диалог — отвечает Claude
    reply, order_details, escalate, power_selection, send_all_photos = get_ai_response(
        chat_id=chat_id,
        user_message=text,
        history=history,
        customer_name=customer_name,
    )

    save_message(chat_id, "user", text)
    save_message(chat_id, "assistant", reply)
    logger.info(f"🤖 [Genex → {customer_name}]: {reply[:100]}...")

    # Отправляем подборку отдельным сообщением перед ответом Claude
    if power_selection:
        await update.message.reply_text(power_selection)

    await update.message.reply_text(reply)

    # Отправляем все 3 фото если клиент попросил
    if send_all_photos:
        for photo_path in ALL_PHOTOS:
            if os.path.exists(photo_path):
                with open(photo_path, "rb") as f:
                    await context.bot.send_photo(chat_id=chat_id, photo=f)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Хотите посмотреть наши реальные объекты? Загляните в наш Instagram — там портфолио выполненных работ:\nhttps://www.instagram.com/genex.kz"
        )

    if any(kw in reply.lower() for kw in MONTAGE_KEYWORDS):
        _schedule_followup(context, chat_id)

    if order_details:
        order_id = save_order(chat_id, customer_name, order_details)
        await notify_manager(
            context=context,
            chat_id=chat_id,
            customer_name=customer_name,
            username=user.username,
            details=order_details,
            order_id=order_id,
        )

    if escalate:
        await notify_manager(
            context=context,
            chat_id=chat_id,
            customer_name=customer_name,
            username=user.username,
            details=f"Требуется помощь менеджера.\nПоследнее сообщение: {text}",
        )


def _build_order_context(history: list, last_message: str, customer_name: str) -> str:
    """Извлекает суть заказа из истории переписки."""
    # Ищем последнее сообщение бота с предложением товара
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if any(w in content.lower() for w in ["кожух", "генератор", "кВт", "perkins", "baudouin", "weichai"]):
                # Берём первые 300 символов контекста
                return f"Клиент: {customer_name} | Обсуждали: {content[:300]}"
    return f"Клиент: {customer_name} | Сообщение: {last_message}"


async def notify_manager(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    customer_name: str,
    username: Optional[str],
    details: str,
    order_id: Optional[int] = None,
):
    manager_id = os.getenv("MANAGER_CHAT_ID")
    if not manager_id:
        return

    username_str = f"@{username}" if username else "нет username"
    subject = f"🔔 НОВАЯ ЗАЯВКА #{order_id}" if order_id else "⚠️ НУЖНА ПОМОЩЬ МЕНЕДЖЕРА"

    text = (
        f"{subject}\n\n"
        f"👤 Клиент: {customer_name} ({username_str})\n"
        f"💬 Chat ID: {chat_id}\n\n"
        f"📋 Детали:\n{details}"
    )

    try:
        await context.bot.send_message(chat_id=int(manager_id), text=text)
    except Exception as e:
        print(f"Ошибка уведомления менеджера: {e}")
