import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
REPORT_CHAT_ID: int = -5137198783

KASPI_SHOPS: list[str] = [
    token
    for key in ("KASPI_TOKEN_1", "KASPI_TOKEN_2")
    if (token := os.environ.get(key))
]
