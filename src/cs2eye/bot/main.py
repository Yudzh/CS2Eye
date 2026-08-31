import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from cs2eye.bot.api_client import CS2EyeAPIClient
from cs2eye.bot.handlers import router
from cs2eye.bot.navigation import NavigationState
from cs2eye.core.config import settings


async def run() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the bot")
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    async with CS2EyeAPIClient(
        settings.cs2eye_api_base_url,
        timeout=settings.cs2eye_api_timeout_seconds,
        generation_timeout=settings.cs2eye_api_generation_timeout_seconds,
    ) as api_client:
        try:
            await dispatcher.start_polling(
                bot, api_client=api_client, navigation_state=NavigationState(),
            )
        finally:
            await bot.session.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
