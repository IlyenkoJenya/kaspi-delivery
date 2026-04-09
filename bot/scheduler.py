# Sends a daily summary to the group chat at 21:00 Almaty time.
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from bot.config import REPORT_CHAT_ID

ALMATY_TZ = ZoneInfo("Asia/Almaty")


async def send_daily_reports(bot: Bot) -> None:
    from bot.services.report import get_today_data

    today = get_today_data()
    reviews = today.get("reviews", [])
    phones = today.get("phones", [])

    if not reviews and not phones:
        print("[Scheduler] Nothing to report today.")
        return

    date_str = datetime.now(ALMATY_TZ).strftime("%d.%m.%Y")
    lines = [f"📊 Отчёт за {date_str}"]

    if deliveries := today.get("deliveries", []):
        lines.append(f"\n📦 Выдано заказов: {len(deliveries)}")
        for d in deliveries:
            who = f", {d['username']}" if d.get("username") else ""
            lines.append(f"  {d['order_id']} — {d['product'][:45]} ({d['time']}{who})")

    if reviews:
        lines.append(f"\n✅ Сгенерировано отзывов: {len(reviews)}")
        for r in reviews:
            who = f", {r['username']}" if r.get("username") else ""
            lines.append(f"  {r['order_id']} — {r['product'][:45]} ({r['time']}{who})")

    if phones:
        lines.append(f"\n📞 Обновлённые номера клиентов: {len(phones)}")
        for p in phones:
            lines.append(f"  Заказ {p['order_id']} — {p['phone']} ({p['time']})")

    text = "\n".join(lines)

    try:
        await bot.send_message(REPORT_CHAT_ID, text)
        print(f"[Scheduler] Report sent to group {REPORT_CHAT_ID}")
    except Exception as e:
        print(f"[Scheduler] Failed to send report: {e}")


async def run_daily_scheduler(bot: Bot) -> None:
    """Runs forever. Fires send_daily_reports once a day at 21:00 Almaty."""
    while True:
        now = datetime.now(ALMATY_TZ)
        target = now.replace(hour=21, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)

        wait_secs = (target - now).total_seconds()
        print(
            f"[Scheduler] Next report at {target.strftime('%Y-%m-%d %H:%M')} Almaty "
            f"(in {wait_secs / 3600:.1f}h)"
        )
        await asyncio.sleep(wait_secs)
        await send_daily_reports(bot)
