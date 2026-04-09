import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
KASPI_EMAIL: str = os.environ["KASPI_EMAIL"]
KASPI_PASS: str = os.environ["KASPI_PASS"]
REPORT_CHAT_ID: int = -5137198783
