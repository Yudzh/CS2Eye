from unittest.mock import AsyncMock, Mock

import pytest

from cs2eye.bot import main


@pytest.mark.parametrize("proxy", ["", "socks5://user:password@172.17.0.1:1080"])
async def test_telegram_proxy_does_not_proxy_internal_api(monkeypatch, proxy):
    monkeypatch.setattr(main.settings, "telegram_bot_token", "test-token")
    monkeypatch.setattr(main.settings, "telegram_proxy_url", proxy)
    session = Mock(close=AsyncMock())
    session_factory = Mock(return_value=session)
    bot = Mock(session=session, set_my_commands=AsyncMock(), set_chat_menu_button=AsyncMock())
    dispatcher = Mock(start_polling=AsyncMock())
    client = AsyncMock()
    api_factory = Mock(return_value=client)
    monkeypatch.setattr(main, "AiohttpSession", session_factory)
    monkeypatch.setattr(main, "Bot", Mock(return_value=bot))
    monkeypatch.setattr(main, "Dispatcher", Mock(return_value=dispatcher))
    monkeypatch.setattr(main, "CS2EyeAPIClient", api_factory)

    await main.run()

    session_factory.assert_called_once_with(proxy=proxy or None)
    assert "proxy" not in api_factory.call_args.kwargs
    dispatcher.start_polling.assert_awaited_once()
    session.close.assert_awaited_once()
