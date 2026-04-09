# Handles switching between shops via the top-right dropdown in Kaspi MC.
# Trigger: .navbar-link inside .navbar-item.has-dropdown
# Options live in .custom-dropdown, active one has .is-active class.


def get_active_shop(page) -> str:
    """Returns something like 'ID - 17727126' for the currently selected shop."""
    try:
        el = page.locator(".custom-dropdown .navbar-item.is-active").first
        if el.count() > 0:
            return el.inner_text().strip()
    except Exception:
        pass
    return ""


def switch_to_next_shop(page) -> bool:
    """Clicks the first non-active shop in the dropdown. Returns True on success."""
    try:
        # Open dropdown
        trigger = page.locator(".navbar-link").first
        trigger.wait_for(state="visible", timeout=10_000)
        trigger.click()
        page.wait_for_timeout(800)

        # Find non-active shop links
        items = page.locator(".custom-dropdown .navbar-item")
        count = items.count()
        print(f"[ShopSwitcher] Found {count} shop(s) in dropdown")

        for i in range(count):
            item = items.nth(i)
            classes = item.get_attribute("class") or ""
            label = item.inner_text().strip()
            if "is-active" not in classes:
                print(f"[ShopSwitcher] Switching to: {label!r}")
                item.click()
                page.wait_for_timeout(3_000)
                new_active = get_active_shop(page)
                print(f"[ShopSwitcher] Now active: {new_active!r}")
                return True

        print("[ShopSwitcher] No other shop found to switch to")
        return False

    except Exception as e:
        print(f"[ShopSwitcher] Error: {e}")
        return False
