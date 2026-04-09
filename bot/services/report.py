import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

ALMATY_TZ = ZoneInfo("Asia/Almaty")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LOG_FILE = os.path.join(DATA_DIR, "reviews_log.json")


def _now_str() -> str:
    return datetime.now(ALMATY_TZ).strftime("%H:%M")


def _today() -> str:
    return datetime.now(ALMATY_TZ).strftime("%Y-%m-%d")


def _load() -> dict:
    if not os.path.exists(LOG_FILE):
        return {}
    with open(LOG_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_delivery(order_id: str, product: str, client_name: str, username: str = "") -> None:
    data = _load()
    today = data.setdefault(_today(), {})
    today.setdefault("deliveries", []).append({
        "order_id": order_id,
        "product": product,
        "client_name": client_name,
        "username": username,
        "time": _now_str(),
    })
    _save(data)
    print(f"[Report] Delivery logged: order={order_id}")


def log_review(order_id: str, product: str, username: str = "") -> None:
    data = _load()
    today = data.setdefault(_today(), {})
    today.setdefault("reviews", []).append({
        "order_id": order_id,
        "product": product,
        "username": username,
        "time": _now_str(),
    })
    _save(data)
    print(f"[Report] Review logged: order={order_id} user={username}")


def log_phone_update(order_id: str, new_phone: str) -> None:
    data = _load()
    today = data.setdefault(_today(), {})
    today.setdefault("phones", []).append({
        "order_id": order_id,
        "phone": new_phone,
        "time": _now_str(),
    })
    _save(data)
    print(f"[Report] Phone logged: order={order_id} phone={new_phone}")


def get_today_data() -> dict:
    data = _load()
    return data.get(_today(), {})
