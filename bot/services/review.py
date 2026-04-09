from openai import AsyncOpenAI
from bot.config import OPENAI_API_KEY

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def generate_review(product_name: str) -> str:
    prompt = (
        f"Напиши 3 коротких, естественных отзыва о товаре «{product_name}». "
        "Упомяни продавца Aquasoft или Аквасофт. "
        "Отзывы 1–3 предложения, пронумерованы."
    )
    response = await _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    text = response.choices[0].message.content or ""
    print(f"[Review] generate_review({product_name!r}) → {text[:80]!r}...")
    return text
