# Runs a Playwright browser in a thread and communicates with the
# asyncio bot handlers through queues.
#
# order_info_queue    session → handler  (dict or None)
# sms_code_queue      handler → session  (4-digit code string)
# phone_queue         handler → session  (phone number string)
# delivery_done_queue session → handler  (True/False)

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright

from bot.agent.kaspi_login import login
from bot.agent.order_scraper import scrape_order
from bot.agent.shop_switcher import switch_to_next_shop

_executor = ThreadPoolExecutor(max_workers=4)

SMS_TIMEOUT = 300      # 5 min to enter SMS code
PHONE_TIMEOUT = 120    # 2 min to enter phone
_CANCEL = object()


class KaspiDeliverySession:

    def __init__(self, user_id: int, notify_fn):
        self.user_id = user_id
        self.notify = notify_fn
        self.loop = asyncio.get_event_loop()

        self.order_info_queue: asyncio.Queue = asyncio.Queue()
        self.sms_code_queue: asyncio.Queue = asyncio.Queue()
        self.phone_queue: asyncio.Queue = asyncio.Queue()
        self.delivery_done_queue: asyncio.Queue = asyncio.Queue()

        self._cancel_event = threading.Event()

    # ── Public ────────────────────────────────────────────────────────────

    async def start(self, order_id: str) -> None:
        """Kick off the browser thread, returns immediately."""
        loop = asyncio.get_event_loop()
        loop.run_in_executor(_executor, self._run_sync, order_id)

    def cancel(self) -> None:
        self._cancel_event.set()
        for q in [self.sms_code_queue, self.phone_queue]:
            try:
                self.loop.call_soon_threadsafe(q.put_nowait, _CANCEL)
            except Exception:
                pass

    # ── Main thread ───────────────────────────────────────────────────────

    def _run_sync(self, order_id: str) -> None:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                page = browser.new_page()
                try:
                    self._flow(page, order_id)
                finally:
                    browser.close()
        except Exception as e:
            print(f"[Session] Fatal error: {e}")
            self._put(self.order_info_queue, None)
            self._put(self.delivery_done_queue, False)

    def _flow(self, page, order_id: str) -> None:
        if self._cancel_event.is_set():
            self._put(self.order_info_queue, None)
            return

        # 1. Login
        try:
            login(page)
        except Exception as e:
            print(f"[Session] Login failed: {e}")
            self._put(self.order_info_queue, None)
            return

        if self._cancel_event.is_set():
            self._put(self.order_info_queue, None)
            return

        # 2. Scrape order info — try current shop, then switch if not found
        order = None
        for shop_attempt in range(2):
            try:
                order = scrape_order(page, order_id)
            except Exception as e:
                print(f"[Session] Scrape error (shop attempt {shop_attempt + 1}): {e}")

            # Found a deliverable order → stop trying
            if order is not None and order.get("error") != "no_deliver_btn":
                break

            if shop_attempt == 0:
                print("[Session] Order not deliverable in shop 1, switching to shop 2...")
                self._notify_sync("🔄 Заказ не найден в первом магазине, проверяю второй...")
                switched = switch_to_next_shop(page)
                if not switched:
                    print("[Session] Could not switch shop")
                    break

        if order is None:
            self._put(self.order_info_queue, None)
            return

        if order.get("error") == "no_deliver_btn":
            # Order exists but can't deliver (wrong status, already delivered, etc.)
            self._put(self.order_info_queue, order)
            self._put(self.delivery_done_queue, False)
            return

        # 3. Click "Выдать заказ" to trigger SMS
        try:
            print("[Session] Clicking 'Выдать заказ'...")
            issue_btn = page.locator("button:has-text('Выдать заказ')").first
            issue_btn.wait_for(state="visible", timeout=30_000)
            issue_btn.click()
        except Exception as e:
            print(f"[Session] Click failed: {e}")
            self._put(self.order_info_queue, None)
            return

        # 4. Determine path: SMS input or phone input?
        try:
            page.wait_for_selector(
                "input[placeholder='Введите SMS-код'], input[placeholder*='SMS'], input[type='tel'], input[placeholder*='телефон']",
                timeout=15_000,
            )
        except Exception:
            print("[Session] No input appeared after clicking 'Выдать заказ'")
            self._put(self.order_info_queue, None)
            return

        # Check which input appeared
        sms_input = page.locator("input[placeholder='Введите SMS-код']")
        phone_input_sel = "input[type='tel'], input[placeholder*='телефон'], input[placeholder*='Телефон']"

        if sms_input.count() > 0:
            # Path A: SMS code required
            order["has_phone"] = True
            self._put(self.order_info_queue, order)
            self._path_a_sms(page, order_id)
        else:
            # Path B: phone input (Kaspi needs client phone first)
            order["has_phone"] = False
            self._put(self.order_info_queue, order)
            self._path_b_phone(page, phone_input_sel, order_id)

    # ── Path A: SMS flow ──────────────────────────────────────────────────

    def _path_a_sms(self, page, order_id: str, max_attempts: int = 3) -> None:
        for attempt in range(1, max_attempts + 1):
            print(f"[Session] Path A: waiting for SMS code (attempt {attempt}/{max_attempts})...")
            code = self._wait_from_bot(self.sms_code_queue, SMS_TIMEOUT)

            if code is _CANCEL or self._cancel_event.is_set():
                self._put(self.delivery_done_queue, False)
                return

            print(f"[Session] Entering SMS code: {code}")
            try:
                sms_input = page.locator("input[placeholder='Введите SMS-код']").first

                # If input is gone, try re-triggering SMS
                if not sms_input.is_visible():
                    print("[Session] SMS input not visible, re-triggering...")
                    issue_btn = page.locator("button:has-text('Выдать заказ')").first
                    if issue_btn.is_visible():
                        issue_btn.click()
                        page.wait_for_selector("input[placeholder='Введите SMS-код']", timeout=15_000)
                        sms_input = page.locator("input[placeholder='Введите SMS-код']").first

                # Fill code (fill() clears existing value automatically)
                # Kaspi enables the confirm button after input — wait briefly
                sms_input.fill(str(code))
                page.wait_for_timeout(800)

                confirm_btn = page.locator("button:has-text('Выдать заказ')").last
                confirm_btn.click()

                # Wait for success modal (shorter timeout — 15s per attempt)
                print("[Session] Waiting for success modal...")
                success = page.locator("text=выдан!")
                success.wait_for(state="visible", timeout=15_000)
                print("[Session] Order delivered!")

                ok_btn = page.locator("button:has-text('OK')").last
                if ok_btn.count() > 0:
                    ok_btn.click()
                    success.wait_for(state="hidden", timeout=20_000)

                self._put(self.delivery_done_queue, True)
                return

            except Exception as e:
                print(f"[Session] Attempt {attempt} failed: {e}")
                if attempt < max_attempts:
                    self._notify_sync(
                        f"❌ Неверный код (попытка {attempt}/{max_attempts}).\n"
                        f"Введите код ещё раз:"
                    )
                    # loop continues — will wait for next code from sms_code_queue
                else:
                    self._notify_sync(
                        f"❌ Исчерпаны все {max_attempts} попытки ввода кода.\n"
                        f"Проверьте заказ вручную: https://kaspi.kz/mc/#/orders/{order_id}"
                    )
                    self._put(self.delivery_done_queue, False)

    # ── Path B: phone flow ────────────────────────────────────────────────

    def _path_b_phone(self, page, phone_sel: str, order_id: str) -> None:
        print("[Session] Path B: waiting for phone from bot...")
        phone = self._wait_from_bot(self.phone_queue, PHONE_TIMEOUT)

        if phone is _CANCEL or self._cancel_event.is_set():
            self._put(self.delivery_done_queue, False)
            return

        print(f"[Session] Entering phone: {phone}")
        try:
            phone_input = page.locator(phone_sel).first
            phone_input.wait_for(state="visible", timeout=10_000)
            phone_input.fill(str(phone))
            page.wait_for_timeout(500)

            # Submit phone
            submit_btn = page.locator("button:has-text('Выдать заказ'), button:has-text('Отправить'), button:has-text('Далее')").first
            submit_btn.click()
            page.wait_for_timeout(3_000)

            # Now check for SMS code input
            sms_input = page.locator("input[placeholder='Введите SMS-код']")
            if sms_input.count() > 0:
                print("[Session] Path B→A: SMS code needed after phone")
                self._notify_sync("📲 SMS отправлен! Введите 4-значный код:")
                code = self._wait_from_bot(self.sms_code_queue, SMS_TIMEOUT)
                if code is _CANCEL:
                    self._put(self.delivery_done_queue, False)
                    return
                sms_input.first.fill(str(code))
                page.wait_for_timeout(1_000)
                page.locator("button:has-text('Выдать заказ')").last.click()

            # Wait for success
            success = page.locator("text=выдан!")
            success.wait_for(state="visible", timeout=60_000)
            print("[Session] Order delivered (path B)!")

            ok_btn = page.locator("button:has-text('OK')").last
            if ok_btn.count() > 0:
                ok_btn.click()

            self._put(self.delivery_done_queue, True)
        except Exception as e:
            print(f"[Session] Path B confirm failed: {e}")
            self._put(self.delivery_done_queue, False)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _wait_from_bot(self, queue: asyncio.Queue, timeout: int):
        future = asyncio.run_coroutine_threadsafe(queue.get(), self.loop)
        try:
            return future.result(timeout=timeout)
        except Exception:
            return _CANCEL

    def _put(self, queue: asyncio.Queue, value) -> None:
        try:
            self.loop.call_soon_threadsafe(queue.put_nowait, value)
        except Exception as e:
            print(f"[Session] Queue put failed: {e}")

    def _notify_sync(self, text: str) -> None:
        future = asyncio.run_coroutine_threadsafe(
            self.notify(text), self.loop
        )
        try:
            future.result(timeout=15)
        except Exception as e:
            print(f"[Session] Notify failed: {e}")
