from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from stagehand_middleware.facade import StagehandFacadeInputError, facade_instructions

from langchain_browserbase import BrowserbaseMiddleware


@pytest.fixture
def middleware():
    with patch("langchain_browserbase.middleware.StagehandFacadeTools") as facade:
        facade.return_value.run = AsyncMock(return_value={"title": "Example"})
        facade.return_value.snapshot = AsyncMock(return_value="[1-1] button Submit")
        facade.return_value.screenshot = AsyncMock(
            return_value={"data": "aW1hZ2U=", "mimeType": "image/png"}
        )
        yield BrowserbaseMiddleware(MagicMock())


async def test_tools_delegate_and_preserve_schemas(middleware):
    run, snapshot, screenshot = middleware.tools
    assert [tool.name for tool in middleware.tools] == ["run", "snapshot", "screenshot"]
    assert "actions" in run.args_schema["properties"]
    assert await run.ainvoke({"code": "return await page.title();"}) == '{"title": "Example"}'
    middleware._facade.run.assert_awaited_once_with(code="return await page.title();")
    assert await snapshot.ainvoke({"includeIframes": False}) == "[1-1] button Submit"
    middleware._facade.snapshot.assert_awaited_once_with(include_iframes=False)
    result = await screenshot.ainvoke(
        {"type": "tool_call", "id": "shot", "name": "screenshot", "args": {"fullPage": True}}
    )
    assert isinstance(result, ToolMessage)
    assert result.content_blocks == [
        {"type": "image", "base64": "aW1hZ2U=", "mime_type": "image/png"}
    ]
    middleware._facade.screenshot.assert_awaited_once_with(full_page=True, type="png", quality=None)


async def test_errors_are_model_visible(middleware):
    run, _, screenshot = middleware.tools
    middleware._facade.run.side_effect = StagehandFacadeInputError("Snapshot IDs are stale")
    assert (
        await run.ainvoke({"actions": [{"op": "click", "id": "1-1"}]}) == "Snapshot IDs are stale"
    )
    assert "Invalid browser" in await screenshot.ainvoke({"quality": 101})
    middleware._facade.screenshot.assert_not_awaited()


async def test_system_message_is_preserved(middleware):
    request = ModelRequest(
        model=MagicMock(), messages=[], system_message=SystemMessage(content="Original instruction")
    )
    handler = AsyncMock(return_value=SimpleNamespace(result=[]))
    await middleware.awrap_model_call(request, handler)
    updated = handler.call_args.args[0]
    assert updated.system_message.content_blocks == [
        {"type": "text", "text": "Original instruction"},
        {"type": "text", "text": facade_instructions()},
    ]
    assert request.system_message.content == "Original instruction"


@pytest.mark.parametrize("provider", ["local", "browserbase"])
async def test_connect_closes_resources(provider):
    browser = SimpleNamespace(close=AsyncMock())
    stagehand = SimpleNamespace(close=AsyncMock())
    module = "browserbase" if provider == "browserbase" else "local_browser"
    with (
        patch(
            f"langchain_browserbase.middleware.{module}.launch",
            AsyncMock(return_value=browser),
        ) as launch,
        patch(
            "langchain_browserbase.middleware.Stagehand.create", AsyncMock(return_value=stagehand)
        ),
    ):
        with pytest.raises(RuntimeError, match="Agent failed"):
            async with BrowserbaseMiddleware.connect(provider=provider, api_key="test-key"):
                raise RuntimeError("Agent failed")
        launch.assert_awaited_once()
        stagehand.close.assert_awaited_once()
        browser.close.assert_awaited_once()


async def test_creation_failure_closes_browser():
    browser = SimpleNamespace(close=AsyncMock())
    with (
        patch(
            "langchain_browserbase.middleware.local_browser.launch", AsyncMock(return_value=browser)
        ),
        patch(
            "langchain_browserbase.middleware.Stagehand.create",
            AsyncMock(side_effect=RuntimeError("startup failed")),
        ),
    ):
        with pytest.raises(RuntimeError, match="startup failed"):
            async with BrowserbaseMiddleware.connect(provider="local"):
                pytest.fail("Should not enter context")
        browser.close.assert_awaited_once()


async def test_agent_executes_browser_tool(middleware):
    class ToolCallingModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            assert {tool.name for tool in tools} == {"run", "snapshot", "screenshot"}
            return self

    model = ToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "snapshot",
                        "args": {},
                        "id": "browser-call",
                    }
                ],
            ),
            AIMessage(content="Found the Submit button"),
        ]
    )
    agent = create_agent(model, middleware=[middleware])
    result = await agent.ainvoke({"messages": [{"role": "user", "content": "Inspect the page"}]})
    assert result["messages"][-1].content == "Found the Submit button"
    assert result["messages"][-2].content == "[1-1] button Submit"


async def test_browserbase_requires_key(monkeypatch):
    monkeypatch.delenv("BROWSERBASE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="BROWSERBASE_API_KEY"):
        async with BrowserbaseMiddleware.connect():
            pytest.fail("Should not enter context")
