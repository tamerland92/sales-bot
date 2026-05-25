import os
import re
from typing import Optional, Tuple
import anthropic
from services.catalog import load_catalog, find_by_power
from services.engine_info import detect_engine, get_engine_info

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """Ты — Genex, AI ассистент магазина ДизельГен.
Всегда представляйся так: "Я Genex — AI ассистент магазина ДизельГен".

О компании: {shop_description}

{catalog}

═══ ЗНАНИЯ О ПРОДУКТЕ ═══

КВт vs КВА:
- кВА — полная мощность генератора
- кВт — полезная мощность после технических потерь
- Номинальная (PRP/Prime Power) — для постоянной/частой работы, длительный режим без перегрузки
- Максимальная (ESP/Standby Power) — резервный режим, кратковременно до 1 часа в 12-часовом цикле

Исполнение:
- Кожух с АВР — звукоизолирующий корпус, для улицы, снижает шум
- Открытое с АВР — без кожуха, только внутри помещения с вентиляцией (под навес нельзя — осадки повредят)
- Контейнерное — для стратегических объектов, с сигнализацией, пожаротушением, вентиляцией, освещением, отоплением

Режим использования (важно для подбора):
- Резервный — работает редко, главное автозапуск и надёжность → ориентир на максимальную мощность
- Постоянный — каждый день, нужен мотор с большим ресурсом и запасом → ориентир на номинальную

Классы (от дешёвого к дорогому): Низкое качество → Бюджетный → средний → Бизнес класс → Премиум класс
Наличие: уточняется при оформлении заказа

═══ ПОЗИЦИОНИРОВАНИЕ GENEX ═══
- GENEX — это качество, поддержка и гарантия. Мы не гонимся за самым дешёвым сегментом.
- У нас всегда есть документы, лицензии, сертификаты, допуски.
- Мы обеспечиваем надёжную работу оборудования и сервис после покупки.
- Если клиент хочет "дешевле всех" — это не к нам. Мы строим бренд надолго.
- Если есть более дешёвые предложения — там часто занижена реальная мощность, щёточный альтернатор, алюминиевая обмотка, нет сервиса.
- Никогда не говори плохо о конкурентах напрямую — просто объясняй ценность GENEX.

═══ МОНТАЖ ═══
После подбора генератора — спроси: "Нужен ли вам монтаж?"
Если да — объясни:
- Выезд специалиста для замера стоит 20 000 тенге (возвращается при покупке у нас)
- Или можно рассчитать без выезда — попроси клиента снять короткое видео:
  1. Где будет стоять генератор
  2. Где находится щитовая (точка подключения)
  3. Маршрут от генератора до щитовой
  4. Способ прокладки кабеля: по воздуху или под землёй
  5. Примерное расстояние (если знает)

КАК РАБОТАТЬ:

ШАГ 1. Клиент называет мощность → сначала уточни единицу измерения:
"Вы указываете мощность в кВт или кВА?

кВт (киловатт) — активная мощность, то что реально потребляет ваше оборудование.
кВА (киловольт-ампер) — полная мощность, включает реактивную составляющую. Обычно на 20-25% больше кВт."

ШАГ 2. После ответа клиента (кВт или кВА) → подборка всех серий уже отправлена отдельным сообщением автоматически.
Ты НЕ повторяешь цены и модели.
Спроси: "Хотите, пришлю фотографии всех трёх исполнений — кожух, открытое и контейнер?"

ШАГ 3. Если клиент говорит да/хочу/пришли/давай на фото → добавь тег [ФОТО_ВСЕ] в конец ответа.
Система автоматически отправит все 3 фото.

ШАГ 4. После того как клиент ответил про доставку (самовывоз или указал город) — попроси имя и телефон для оформления заявки.

ШАГ 5. Как только клиент написал номер телефона — система автоматически оформит заявку.
Ты НЕ должен переспрашивать "правильно ли я понял", "верно ли указаны данные" и т.д.

ШАГ 6. Сложный технический вопрос → добавь: [ПЕРЕДАТЬ_МЕНЕДЖЕРУ: причина]

Правила:
- Пиши на русском, дружелюбно и кратко
- Цены из каталога, не придумывай
- Наличие: "уточняется при заказе"
- Двигатели Ricardo — класс "низкое качество". Показывай только цену, без каких-либо комментариев о надёжности или качестве.
- СТРОГО ЗАПРЕЩЕНО спрашивать "резервный или постоянный?" и "цена или надёжность?"
- Фото отправляются системой автоматически — тебе нужно только спросить "Хотите, пришлю фото?" и добавить тег [ФОТО_ВСЕ] если клиент согласен.
{power_block}"""


def _extract_power(text: str) -> Tuple[Optional[float], str]:
    """Возвращает (значение, единица) — 'kw' или 'kva'."""
    text_lower = text.lower()

    # Сначала ищем кВА
    for pattern in [r'(\d+[\.,]?\d*)\s*ква', r'(\d+[\.,]?\d*)\s*kva']:
        m = re.search(pattern, text_lower)
        if m:
            try:
                return float(m.group(1).replace(",", ".")), "kva"
            except Exception:
                pass

    # Потом кВт
    for pattern in [r'(\d+[\.,]?\d*)\s*кв[тw]', r'(\d+[\.,]?\d*)\s*kwh?',
                    r'(\d+[\.,]?\d*)\s*квт', r'мощност[ьи]\w*\s+(\d+[\.,]?\d*)']:
        m = re.search(pattern, text_lower)
        if m:
            try:
                return float(m.group(1).replace(",", ".")), "kw"
            except Exception:
                pass

    return None, "kw"


def _has_phone(text: str) -> bool:
    return bool(re.search(r'[\+\d][\d\s\-\(\)]{8,}', text))


def _has_name(text: str) -> bool:
    keywords = ['меня зовут', 'мое имя', 'моё имя', 'зовут', 'я ']
    text_lower = text.lower()
    return any(k in text_lower for k in keywords) or (
        len(text.split()) >= 2 and any(w[0].isupper() for w in text.split())
    )


def get_ai_response(
    chat_id: int,
    user_message: str,
    history: list,
    customer_name: str = ""
) -> Tuple[str, Optional[str], bool, Optional[str]]:
    shop_name = os.getenv("SHOP_NAME", "Магазин ДизельГен")
    shop_description = os.getenv("SHOP_DESCRIPTION", "")
    catalog = load_catalog()

    # Если клиент согласился на фото — перехватываем, не зовём Claude
    AGREE_WORDS = ["да", "хочу", "давай", "отправь", "пришли", "конечно", "ок", "ok", "yes", "👍"]
    asked_photos = any(
        "хотите" in msg.get("content", "").lower() and "фото" in msg.get("content", "").lower()
        for msg in history[-4:] if msg.get("role") == "assistant"
    )
    if asked_photos and any(w in user_message.lower() for w in AGREE_WORDS):
        reply = (
            "Отправляю!\n\n"
            "Указанные цены действительны при самовывозе из г. Алматы. "
            "Если вам необходима доставка — пожалуйста, укажите адрес или населённый пункт назначения, "
            "и мы рассчитаем стоимость."
        )
        return reply, None, False, None, True

    # Подборка по мощности — только из текущего сообщения
    target, unit = _extract_power(user_message)
    power_block = ""
    raw_selection = ""
    if target:
        raw_selection = find_by_power(target, unit)
        if raw_selection:
            # Проверяем только последнее сообщение бота — спрашивал ли он про фото именно сейчас
            last_bot = next((m for m in reversed(history) if m.get("role") == "assistant"), None)
            already_shown = (
                last_bot is not None and
                "хотите" in last_bot.get("content", "").lower() and
                "фото" in last_bot.get("content", "").lower()
            )
            if not already_shown:
                # Пропускаем Claude — сразу возвращаем фиксированный ответ
                reply = "Хотите, пришлю фотографии всех трёх исполнений — кожух, открытое и контейнер?"
                return reply, None, False, raw_selection, False

    # Описание двигателя с сайта
    engine_name = detect_engine(user_message)
    if engine_name:
        info = get_engine_info(engine_name)
        if info:
            power_block += f"\n\n{info}\n(Перескажи клиенту кратко — 3-4 предложения.)"

    # Если клиент дал имя И телефон — принудительно оформляем заказ
    auto_order_hint = ""
    if _has_phone(user_message) and _has_name(user_message):
        auto_order_hint = (
            "\n\nВНИМАНИЕ: клиент только что оставил своё имя и телефон. "
            "Немедленно подтверди заказ и добавь тег [ЗАКАЗ: детали заказа, имя, телефон]."
        )
        power_block += auto_order_hint

    system = SYSTEM_PROMPT.format(
        shop_name=shop_name,
        shop_description=shop_description,
        catalog=catalog,
        power_block=power_block,
    )

    messages = history + [{"role": "user", "content": user_message}]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system,
        messages=messages,
    )

    full_text = response.content[0].text
    order_details = None
    escalate = False
    clean_text = full_text

    if "[ЗАКАЗ:" in full_text:
        start = full_text.index("[ЗАКАЗ:") + len("[ЗАКАЗ:")
        end = full_text.index("]", start)
        order_details = full_text[start:end].strip()
        clean_text = full_text[:full_text.index("[ЗАКАЗ:")].strip()

    if "[ПЕРЕДАТЬ_МЕНЕДЖЕРУ:" in full_text:
        escalate = True
        clean_text = full_text[:full_text.index("[ПЕРЕДАТЬ_МЕНЕДЖЕРУ:")].strip()

    send_all_photos = "[ФОТО_ВСЕ]" in full_text
    if send_all_photos:
        clean_text = clean_text.replace("[ФОТО_ВСЕ]", "").strip()

    return clean_text, order_details, escalate, raw_selection or None, send_all_photos
