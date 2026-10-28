from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from stagehand_middleware.facade import StagehandFacadeInputError

from langchain_stagehand import StagehandMiddleware


@pytest.fixture
def middleware():
    with (
        patch("langchain_stagehand.middleware.Stagehand.create", AsyncMock()),
        patch("langchain_stagehand.middleware.StagehandFacadeTools") as facade,
    ):
        facade.return_value.run = AsyncMock(return_value={"title": "Example"})
        facade.return_value.snapshot = AsyncMock(return_value="[1-1] button Submit")
        facade.return_value.screenshot = AsyncMock(
            return_value={"data": "aW1hZ2U=", "mimeType": "image/png"}
        )
        facade.return_value.close = AsyncMock()
        middleware = StagehandMiddleware(browser=MagicMock())
        middleware.facade = facade.return_value
        yield middleware


async def test_tools_delegate_and_preserve_schemas(middleware):
    run, snapshot, screenshot = middleware.tools
    assert [tool.name for tool in middleware.tools] == ["run", "snapshot", "screenshot"]
    assert "actions" in run.get_input_schema().model_json_schema()["properties"]
    assert await run.ainvoke({"code": "return await page.title();"}) == '{"title": "Example"}'
    middleware.facade.run.assert_awaited_once_with(code="return await page.title();", actions=None)
    assert await snapshot.ainvoke({"includeIframes": False}) == "[1-1] button Submit"
    middleware.facade.snapshot.assert_awaited_once_with(include_iframes=False)
    result = await screenshot.ainvoke(
        {"type": "tool_call", "id": "shot", "name": "screenshot", "args": {"fullPage": True}}
    )
    assert isinstance(result, ToolMessage)
    assert result.content_blocks == [
        {"type": "image", "base64": "aW1hZ2U=", "mime_type": "image/png"}
    ]
    middleware.facade.screenshot.assert_awaited_once_with(full_page=True, type="png", quality=None)


async def test_errors_are_model_visible(middleware):
    run, _, screenshot = middleware.tools
    middleware.facade.run.side_effect = StagehandFacadeInputError("Snapshot IDs are stale")
    assert (
        await run.ainvoke({"actions": [{"op": "click", "id": "1-1"}]}) == "Snapshot IDs are stale"
    )
    assert "validation error" in await screenshot.ainvoke({"quality": 101})
    assert "validation error" in await run.ainvoke({"actions": [{"op": "fill", "id": "1-1"}]})
    middleware.facade.screenshot.assert_not_awaited()


def test_tool_descriptions_include_browser_guidance(middleware):
    run, snapshot, screenshot = middleware.tools
    assert "Playwright" in run.description
    assert "do not launch another browser" in run.description
    assert "after navigation or stale IDs" in run.description
    assert "after navigation or stale IDs" in snapshot.description
    assert "screenshot" in screenshot.description


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
    result = await agent.ainvoke({"messages": [{"role": "user", "content": "Again"}]})
    assert result["messages"][-1].content == "Found the Submit button"
    middleware.facade.close.assert_not_awaited()


async def test_aclose_detaches_and_a_later_call_reattaches(middleware):
    run = middleware.tools[0]
    for _ in range(2):
        await run.ainvoke({"code": "return 1;"})
        await middleware.aclose()
    assert middleware.facade.close.await_count == 2
    await middleware.aclose()  # nothing attached: no-op
    assert middleware.facade.close.await_count == 2


async def test_connection_error_detaches(middleware):
    run = middleware.tools[0]
    middleware.facade.run.side_effect = ConnectionError("socket closed")
    assert "ConnectionError: socket closed" in await run.ainvoke({"code": "return 1;"})
    middleware.facade.close.assert_awaited_once()
