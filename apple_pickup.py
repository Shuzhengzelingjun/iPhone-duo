from datetime import datetime, timezone

import requests

PART_NUMBERS = ["MK2H4X/A", "MK2F4X/A"]
POSTCODE = "2000"
PICKUP_URL = "https://www.apple.com/au/shop/retail/pickup-message"


def buy_url(part_number):
    return f"https://www.apple.com/au/shop/product/{part_number}"


def fetch_availability(part_numbers=None, postcode=None):
    part_numbers = list(part_numbers or PART_NUMBERS)
    postcode = postcode or POSTCODE
    params = {"pl": "true", "location": postcode}
    for index, part_number in enumerate(part_numbers):
        params[f"parts.{index}"] = part_number

    response = requests.get(
        PICKUP_URL,
        params=params,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    stores_raw = payload["body"]["stores"]

    stores = []
    available = []
    for store in stores_raw:
        parts = []
        for part_number in part_numbers:
            stock = store.get("partsAvailability", {}).get(part_number, {})
            title = (
                stock.get("messageTypes", {})
                .get("regular", {})
                .get("storePickupProductTitle", part_number)
            )
            status = stock.get("pickupDisplay", "unknown")
            quote = (
                stock.get("pickupSearchQuote")
                or stock.get("storePickupQuote")
                or stock.get("pickupQuote")
                or ""
            )
            item = {
                "partNumber": part_number,
                "title": title,
                "status": status,
                "quote": quote,
                "buyUrl": buy_url(part_number),
            }
            parts.append(item)
            if status == "available":
                available.append(
                    {
                        "store": store.get("storeName"),
                        "partNumber": part_number,
                        "title": title,
                        "quote": quote,
                        "buyUrl": buy_url(part_number),
                    }
                )
        stores.append(
            {
                "name": store.get("storeName"),
                "city": store.get("city"),
                "distance": store.get("storeDistanceWithUnit"),
                "parts": parts,
            }
        )

    return {
        "postcode": postcode,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "available": available,
        "stores": stores,
    }
