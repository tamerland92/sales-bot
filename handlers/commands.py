import os
from telegram import Update
from telegram.ext import ContextTypes

from database.db import get_all_orders


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    shop_name = os.getenv("SHOP_NAME", "Магазин ДизельГен")
    assistant_name = os.getenv("BOT_ASSISTANT_NAME", "Genex")
    await update.message.reply_text(
        f"Привет! Я Genex — AI ассистент магазина ДизельГен.\n\n"
        "Помогу вам:\n"
        "• Подобрать генератор по мощности и бюджету\n"
        "• Узнать цены и сравнить варианты\n"
        "• Оформить заказ\n\n"
        "Напишите что вас интересует!"
    )


async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /orders — только для менеджера."""
    manager_id = os.getenv("MANAGER_CHAT_ID")
    if str(update.effective_chat.id) != str(manager_id):
        return

    orders = get_all_orders()
    if not orders:
        await update.message.reply_text("Заказов пока нет.")
        return

    lines = ["📦 Последние заказы:\n"]
    for order in orders[:10]:
        order_id, customer, details, status, ts = order
        date = ts[:10] if ts else "?"
        lines.append(f"#{order_id} [{date}] {customer}\n{details}\nСтатус: {status}\n")

    await update.message.reply_text("\n".join(lines))
