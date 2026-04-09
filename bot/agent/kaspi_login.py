from bot.config import KASPI_EMAIL, KASPI_PASS


def login(page) -> None:
    print("[Login] Opening Kaspi login page...")
    page.goto("https://kaspi.kz/mc/")
    page.wait_for_selector("#user_email_field", timeout=60_000)

    print("[Login] Entering email...")
    page.fill("#user_email_field", KASPI_EMAIL)
    page.locator("button:has-text('Продолжить')").click()

    page.wait_for_selector("#password_field", timeout=60_000)

    print("[Login] Entering password...")
    page.fill("#password_field", KASPI_PASS)
    page.keyboard.press("Enter")

    page.wait_for_url("**/#/**", timeout=60_000)
    page.wait_for_timeout(3_000)
    print("[Login] Logged in successfully")
