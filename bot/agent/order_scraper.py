def scrape_order(page, order_id: str) -> dict | None:
    """
    Go to the order page and pull out what we need.
    Returns None if the order wasn't found or the page errored out.
    """
    print(f"[Scraper] Navigating to order {order_id}...")

    # Navigate away first to force SPA re-render
    page.goto("https://kaspi.kz/mc/#/orders-new?status=DELIVERY")
    page.wait_for_timeout(1_500)

    # Now navigate to specific order
    page.goto(f"https://kaspi.kz/mc/#/orders/{order_id}")

    # Wait until the page shows THIS order's number (guards against stale SPA content)
    try:
        page.wait_for_selector(f"text=Заказ №{order_id}", timeout=25_000)
    except Exception:
        body_text = page.locator("body").inner_text()
        if "не найден" in body_text.lower() or "not found" in body_text.lower():
            print(f"[Scraper] Order {order_id} not found")
            return None
        # Order number not shown — might be invalid or not accessible
        print(f"[Scraper] Order {order_id} title not found on page")
        return None

    # Wait for buyer info to be populated
    try:
        page.wait_for_selector(".buyer-info", timeout=10_000)
    except Exception:
        pass  # continue anyway, buyer-info might not exist for some order types

    # --- Client name ---
    client_name = ""
    try:
        el = page.locator(".buyer-info__block-value span.has-text-weight-medium").first
        if el.count() > 0:
            client_name = el.inner_text().strip()
    except Exception:
        pass

    # --- Product name ---
    product = ""
    try:
        # Partial match covers "Название в Kaspi Магазине" and any shop-specific variants
        el = page.locator('td[data-label*="Название"]').first
        if el.count() > 0:
            product = el.inner_text().strip()
    except Exception:
        pass

    if not product:
        # Fallback: first td that looks like a product name (not a date/number/status)
        import re
        date_re = re.compile(r"^\d{2}\.\d{2}\.\d{4}")
        try:
            tds = page.locator("td")
            for i in range(min(tds.count(), 20)):
                text = tds.nth(i).inner_text().strip()
                if (
                    len(text) > 5
                    and not text[:1].isdigit()
                    and not date_re.match(text)
                ):
                    product = text
                    break
        except Exception:
            pass

    # --- Phone number ---
    phone = ""
    try:
        el = page.locator('a[href^="tel:"]').first
        if el.count() > 0:
            raw = el.inner_text().strip()
            phone = raw.split(",")[0].strip()   # take first number if multiple
    except Exception:
        pass

    # --- Deliver button ---
    has_deliver_btn = page.locator("button:has-text('Выдать заказ')").count() > 0

    print(f"[Scraper] product={product!r} client={client_name!r} phone={phone!r} deliver_btn={has_deliver_btn}")

    if not has_deliver_btn:
        return {
            "product": product or f"Заказ #{order_id}",
            "client_name": client_name or "—",
            "phone": phone,
            "has_phone": False,
            "error": "no_deliver_btn",
        }

    return {
        "product": product or f"Заказ #{order_id}",
        "client_name": client_name or "—",
        "phone": phone,
        "has_phone": True,  # refined after click in delivery_session
    }
