import json
import requests
from bot.config import KASPI_SHOPS

_BASE = "https://kaspi.kz/shop/api/v2"
_HEADERS = {
    "Content-Type": "application/vnd.api+json",
    "User-Agent": "PostmanRuntime/7.37.3",
}


def _headers(token: str, security_code: str = "", send_code: bool = True) -> dict:
    return {
        **_HEADERS,
        "X-Auth-Token": token,
        "X-Security-Code": security_code,
        "X-Send-Code": "true" if send_code else "false",
    }


def _order_payload(order_id: str, order_code: str) -> str:
    return json.dumps({
        "data": {
            "type": "orders",
            "id": order_id,
            "attributes": {"code": order_code, "status": "COMPLETED"},
        }
    })


def find_order(order_code: str) -> tuple[dict | None, str | None]:
    """Try each shop token; return (order_data, token) for the first match."""
    for token in KASPI_SHOPS:
        try:
            r = requests.get(
                f"{_BASE}/orders?filter[orders][code]={order_code}",
                headers={**_HEADERS, "X-Auth-Token": token},
                timeout=30,
            )
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    return data[0], token
        except Exception:
            continue
    return None, None


def get_order_product(order_id: str, token: str) -> str:
    try:
        r = requests.get(
            f"{_BASE}/orders/{order_id}/entries",
            headers={**_HEADERS, "X-Auth-Token": token},
            timeout=30,
        )
        if r.status_code == 200:
            entries = r.json().get("data", [])
            if entries:
                attrs = entries[0].get("attributes", {})
                offer = attrs.get("offer", {})
                if isinstance(offer, dict):
                    for field in ("name", "nameRu", "title"):
                        if offer.get(field):
                            return offer[field]
    except Exception as e:
        import logging
        logging.warning(f"[kaspi_api] get_order_product error: {e}")
    return "—"


def send_delivery_code(order_id: str, order_code: str, token: str) -> tuple[bool, str]:
    """Step 1: trigger SMS to customer (X-Send-Code: true)."""
    try:
        r = requests.post(
            f"{_BASE}/orders",
            headers=_headers(token, "", True),
            data=_order_payload(order_id, order_code),
            timeout=30,
        )
        return r.status_code < 500, r.text
    except Exception as e:
        return False, str(e)


def confirm_delivery(order_id: str, order_code: str, token: str, sms_code: str) -> tuple[bool, str]:
    """Step 2: confirm delivery with SMS code (X-Send-Code: false)."""
    try:
        r = requests.post(
            f"{_BASE}/orders",
            headers=_headers(token, sms_code, False),
            data=_order_payload(order_id, order_code),
            timeout=30,
        )
        return r.status_code in (200, 201, 204), r.text
    except Exception as e:
        return False, str(e)
