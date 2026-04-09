# Kaspi Delivery Bot

Telegram bot for confirming Kaspi order deliveries. Automates the "Выдать заказ" flow via Playwright — logs in, finds the order, handles SMS confirmation, and optionally generates review suggestions via OpenAI.

Built for shop staff/couriers who process orders through Kaspi Merchant Cabinet.

## Running

```bash
source venv/bin/activate
python -m bot.main
```

## Stack

- Python 3.12, aiogram 3.7.0, Playwright 1.44.0, openai>=1.0.0
- Playwright runs on sync API inside a ThreadPoolExecutor. Bot and browser talk through asyncio queues.
- FSM state stored in memory (MemoryStorage) — no DB needed

## Project layout

```
bot/
  main.py                 # entry point: starts polling + daily scheduler
  config.py               # loads .env; REPORT_CHAT_ID is hardcoded
  scheduler.py            # sends daily report at 21:00 Almaty time to group
  agent/
    kaspi_login.py        # logs into kaspi.kz/mc/
    order_scraper.py      # grabs order details from the order page
    shop_switcher.py      # switches between shops via the navbar dropdown
    delivery_session.py   # orchestrates the full delivery flow
  handlers/
    order.py              # FSM handlers: order_id → SMS/phone → review
    cancel.py             # /cancel
  states/order_states.py  # OrderFlow state group
  keyboards/inline.py     # inline keyboards for phone confirm + review prompts
  services/
    report.py             # logging deliveries/reviews/phones to JSON
    review.py             # generates review text via gpt-4o-mini
  data/reviews_log.json   # persistent log: {date: {deliveries, reviews, phones}}
```

## FSM flow

| State | What happens |
|---|---|
| `waiting_order_id` | User types an order number |
| `waiting_code` | User enters the 4-digit SMS code (up to 3 tries) |
| `waiting_phone` | Path B: Kaspi asks for client phone before sending SMS |
| `waiting_phone_confirm` | "Do you have the client's real number?" |
| `waiting_phone_update` | User types the corrected phone number |
| `waiting_review_decision` | "Generate review suggestions?" |

## Kaspi-specific gotchas

**SPA cache** — always navigate to a different page before going to the order URL, otherwise you sometimes get stale content from the previous order.

**Two shops** — if shop 1 doesn't have a "Выдать заказ" button, the bot automatically switches to shop 2 and retries. This covers the case where the order belongs to the other shop.

**SMS retry** — up to 3 attempts. The `awaiting_delivery` flag in FSM state prevents duplicate listeners if the user sends multiple codes quickly.

**Disabled buttons** — `wait_for(state="enabled")` doesn't reliably work on Kaspi's CSS-disabled buttons. Using a fixed `wait_for_timeout(800)` after `fill()` instead.

**Product name selector** — `td[data-label*="Название"]` uses partial match so it works across both shops regardless of the exact column label.

## Working selectors

```
Client name:   .buyer-info__block-value span.has-text-weight-medium
Product:       td[data-label*="Название"]
Phone:         a[href^="tel:"]
Deliver btn:   button:has-text('Выдать заказ')
SMS input:     input[placeholder='Введите SMS-код']
Success modal: text=выдан!
```

## Daily report format

```
Отчёт за dd.mm.yyyy

Выдано заказов: N
  order_id — product (HH:MM, @username)

Сгенерировано отзывов: N
  order_id — product (HH:MM, @username)

Обновлённые номера клиентов: N
  Заказ order_id — phone (HH:MM)
```

## Triggering the report manually

```bash
python3 -c "
import asyncio, sys; sys.path.insert(0, '.')
from bot.config import TELEGRAM_BOT_TOKEN
from bot.scheduler import send_daily_reports
from aiogram import Bot
async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await send_daily_reports(bot)
    await bot.session.close()
asyncio.run(main())
"
```

## .env

```
TELEGRAM_BOT_TOKEN=
OPENAI_API_KEY=
KASPI_EMAIL=
KASPI_PASS=
```
# kaspi-delivery
