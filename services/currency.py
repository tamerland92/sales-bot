import time
import urllib.request
import xml.etree.ElementTree as ET

_cache = {"rate": None, "ts": 0}
RATE_TTL = 6 * 3600  # обновляем раз в 6 часов


def get_usd_kzt() -> float:
    if _cache["rate"] and (time.time() - _cache["ts"]) < RATE_TTL:
        return _cache["rate"]
    try:
        with urllib.request.urlopen(
            "https://nationalbank.kz/rss/rates_all.xml", timeout=5
        ) as resp:
            root = ET.fromstring(resp.read())
        for item in root.iter("item"):
            title = item.find("title")
            desc = item.find("description")
            if title is not None and "USD" in title.text and desc is not None:
                rate = float(desc.text.replace(",", ".").strip())
                _cache["rate"] = rate
                _cache["ts"] = time.time()
                return rate
    except Exception:
        pass
    return _cache["rate"] or 472.0
