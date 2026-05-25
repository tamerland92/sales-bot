import re
import time
import requests
from html.parser import HTMLParser

BASE_URL = "https://www.gc-azimut.ru/engines"

# Маппинг названий двигателей → URL slug на сайте
ENGINE_SLUGS = {
    "perkins":   "perkins",
    "baudouin":  "baudouin",
    "weichai":   "weichai",
    "yuchai":    "yuchai",
    "yangdong":  "yangdong",
    "sdec":      "sdec",
    "kofo":      "kofo",
    "ricardo":   "ricardo",
    "woling":    "woling",
    "cummins":   "cummins",
    "deutz":     "deutz",
    "doosan":    "doosan",
    "fpt":       "fpt",
    "isuzu":     "isuzu",
    "kubota":    "kubota",
    "mitsubishi": "mitsubishi",
    "mtu":       "mtu",
    "scania":    "scania",
    "volvo":     "volvo-penta",
    "mmz":       "mmz",
    "ymz":       "ymz",
}

_cache = {}
CACHE_TTL = 3600  # кешируем на 1 час


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)


def _fetch_engine_page(slug: str) -> str:
    now = time.time()
    if slug in _cache and now - _cache[slug]["ts"] < CACHE_TTL:
        return _cache[slug]["text"]

    url = f"{BASE_URL}/{slug}/"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        parser = _TextExtractor()
        parser.feed(resp.text)
        raw = " ".join(parser.text_parts)
        # Убираем повторяющиеся пробелы
        text = re.sub(r'\s+', ' ', raw).strip()
        # Берём первые 3000 символов — этого достаточно для описания
        text = text[:3000]
        _cache[slug] = {"text": text, "ts": now}
        return text
    except Exception as e:
        return f"Не удалось получить информацию о двигателе: {e}"


def detect_engine(text: str):
    """Определяет название двигателя из текста клиента."""
    text_lower = text.lower()
    for name in ENGINE_SLUGS:
        if name in text_lower:
            return name
    return None


def get_engine_info(engine_name: str) -> str:
    """Возвращает текст со страницы двигателя для передачи в Claude."""
    slug = ENGINE_SLUGS.get(engine_name.lower())
    if not slug:
        return ""
    text = _fetch_engine_page(slug)
    return f"\nИнформация о двигателе {engine_name.capitalize()} с сайта производителя:\n{text}"
