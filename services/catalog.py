import os
import json
import time
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

_cache = {"text": None, "rows": [], "ts": 0}
CACHE_TTL = 300

IDX_NOM_KW  = 1
IDX_NOM_KVA = 2
IDX_MAX_KW  = 3
IDX_MAX_KVA = 4
IDX_ENGINE  = 5
IDX_MODEL   = 6
IDX_ALTERNATOR = 7
IDX_CABINET = 8
IDX_OPEN    = 9
IDX_VARIANT = 11


def _get_client():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)


def _parse_kw(value: str) -> float:
    try:
        return float(value.replace(",", ".").strip())
    except Exception:
        return 0.0


def _load_from_sheet():
    global _cache
    if _cache["text"] and (time.time() - _cache["ts"]) < CACHE_TTL:
        return

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        return

    client = _get_client()
    sheet = client.open_by_key(sheet_id).sheet1
    all_values = sheet.get_all_values()

    if len(all_values) < 4:
        return

    data_rows = all_values[3:]
    rows = []
    lines = ["Каталог дизельных генераторов:\n"]

    for row in data_rows:
        if len(row) <= IDX_NOM_KW or not row[IDX_NOM_KW]:
            continue

        nom_kw_str  = row[IDX_NOM_KW]
        nom_kva_str = row[IDX_NOM_KVA] if len(row) > IDX_NOM_KVA else ""
        max_kw_str  = row[IDX_MAX_KW]  if len(row) > IDX_MAX_KW  else ""
        max_kva_str = row[IDX_MAX_KVA] if len(row) > IDX_MAX_KVA else ""
        nom_kw  = _parse_kw(nom_kw_str)
        nom_kva = _parse_kw(nom_kva_str)
        max_kw  = _parse_kw(max_kw_str)
        max_kva = _parse_kw(max_kva_str)
        engine  = row[IDX_ENGINE]  if len(row) > IDX_ENGINE  else ""
        model   = row[IDX_MODEL]   if len(row) > IDX_MODEL   else ""
        alternator   = row[IDX_ALTERNATOR] if len(row) > IDX_ALTERNATOR else ""
        price_cabinet = row[IDX_CABINET]   if len(row) > IDX_CABINET    else ""
        price_open    = row[IDX_OPEN]      if len(row) > IDX_OPEN       else ""
        variant       = row[IDX_VARIANT]   if len(row) > IDX_VARIANT    else ""

        rows.append({
            "nom_kw":  nom_kw,
            "nom_kva": nom_kva,
            "max_kw":  max_kw,
            "max_kva": max_kva,
            "engine": engine,
            "model": model,
            "alternator": alternator,
            "price_cabinet": price_cabinet,
            "price_open": price_open,
            "variant": variant.lower().strip(),
        })

        line = f"• Ном: {nom_kw_str} кВт / {nom_kva_str} кВА | Макс: {max_kw_str} кВт / {max_kva_str} кВА | {engine} {model}"
        if alternator:
            line += f" | Альт: {alternator}"
        if price_cabinet:
            line += f" | Кожух с АВР: {price_cabinet}"
        if price_open:
            line += f" | Открытый с АВР: {price_open}"
        if variant:
            line += f" | Класс: {variant}"
        lines.append(line)

    _cache = {"text": "\n".join(lines), "rows": rows, "ts": time.time()}


def load_catalog() -> str:
    try:
        _load_from_sheet()
        return _cache["text"] or "Каталог временно недоступен."
    except Exception as e:
        return f"Не удалось загрузить каталог: {e}"


# Порядок классов от дешёвого к дорогому
CLASS_ORDER = ["низкое качество", "бюджетный", "средний", "бизнес класс", "премиум класс"]


def find_by_power(target: float, unit: str = "kw", tolerance: float = 0.30) -> str:
    """
    unit='kw'  → ищет по номинальной кВт, показывает ном. кВт / ном. кВА
    unit='kva' → ищет по максимальной кВА, показывает макс. кВт / макс. кВА
    """
    try:
        _load_from_sheet()
    except Exception:
        return ""

    rows = _cache.get("rows", [])
    if not rows:
        return ""

    field = "nom_kw" if unit == "kw" else "max_kva"
    low  = target * (1 - tolerance)
    high = target * (1 + tolerance)
    candidates = [r for r in rows if low <= r[field] <= high]

    if not candidates:
        low  = target * 0.5
        high = target * 1.5
        candidates = [r for r in rows if low <= r[field] <= high]

    if not candidates:
        return ""

    unit_label = "кВт (номинальная)" if unit == "kw" else "кВА (максимальная)"

    SERIES_NAME = {
        "низкое качество": "Серия «Эконом»",
        "бюджетный":       "Серия «Бюджет»",
        "средний":         "Серия «Стандарт»",
        "бизнес класс":    "Серия «Бизнес»",
        "премиум класс":   "Серия «Премиум»",
    }
    SERIES_DESC = {
        "низкое качество": "Низкая цена = низкое качество. Только для очень редкого резервного использования.",
        "бюджетный":       "Аварийное резервное электроснабжение. До ~150 мото-часов в месяц.",
        "средний":         "Резервное и периодическое использование. Стабильное качество, увеличенный моторесурс.",
        "бизнес класс":    "Резервная и постоянная эксплуатация. Высокий моторесурс, развитая сервисная поддержка.",
        "премиум класс":   "Промышленный уровень. Круглосуточная эксплуатация, максимальная надёжность.",
    }

    # 3 ближайших уровня мощности
    unique_vals = sorted(set(r[field] for r in candidates), key=lambda x: abs(x - target))
    top_vals = sorted(unique_vals[:3])

    blocks = [f"Подборка генераторов ~{target} {unit_label}:\n"]

    for val in top_vals:
        val_rows = [r for r in candidates if r[field] == val]
        if unit == "kw":
            kva = val_rows[0]["nom_kva"] if val_rows else ""
            blocks.append(f"=== {val} кВт / {kva} кВА ===\n")
        else:
            kw = val_rows[0]["max_kw"] if val_rows else ""
            blocks.append(f"=== {kw} кВт / {val} кВА ===\n")

        for cls in CLASS_ORDER:
            matches = [r for r in val_rows if r["variant"] == cls]
            if not matches:
                continue
            name = SERIES_NAME.get(cls, cls)
            desc = SERIES_DESC.get(cls, "")
            for match in matches:
                cl = f"{name} — {match['engine']} {match['model']}\n"
                cl += f"{desc}\n"
                cl += f"Номинальная мощность: {match['nom_kw']} кВт / {match['nom_kva']} кВА\nМаксимальная мощность: {match['max_kw']} кВт / {match['max_kva']} кВА"
                if match["price_cabinet"]:
                    cl += f"\nКожух с АВР: {match['price_cabinet']}"
                if match["price_open"]:
                    cl += f"\nОткрытое с АВР: {match['price_open']}"
                cl += "\nКонтейнерное исполнение — цена по запросу"
                blocks.append(cl)
                blocks.append("")

    return "\n".join(blocks)
