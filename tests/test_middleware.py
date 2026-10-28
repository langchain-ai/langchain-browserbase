from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from stagehand_middleware.facade import StagehandFacadeInputError, facade_instructions

from langchain_stagehand import StagehandMiddleware


@pytest.fixture
def middleware():
    with patch("langchain_stagehand.middleware.StagehandFacadeTools") as facade:
        facade.return_value.run = AsyncMock(return_value={"title": "Example"})
        facade.return_value.snapshot = AsyncMock(return_value="[1-1] button Submit")
        facade.return_value.screenshot = AsyncMock(
            return_value={"data": "aW1hZ2U=", "mimeType": "image/png"}
        )
        facade.return_value.close = AsyncMock()
        yield StagehandMiddleware(stagehand=MagicMock())


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
        model=MagicMock(),
        messages=[],
        system_message=SystemMessage(
            content="Original instruction", name="policy", additional_kwargs={"custom": "value"}
        ),
    )
    handler = AsyncMock(return_value=SimpleNamespace(result=[]))
    await middleware.awrap_model_call(request, handler)
    updated = handler.call_args.args[0]
    assert updated.system_message.content_blocks == [
        {"type": "text", "text": "Original instruction"},
        {"type": "text", "text": facade_instructions()},
    ]
    assert request.system_message.content == "Original instruction"
    assert updated.system_message.name == "policy"
    assert updated.system_message.additional_kwargs == {"custom": "value"}


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
    middleware._facade.close.assert_awaited_once()


async def test_lifecycle_closes_client(middleware):
    await middleware.abefore_agent({}, MagicMock())
    await middleware.aafter_agent({}, MagicMock())
    middleware._facade.close.assert_awaited_once()
    with pytest.raises(RuntimeError, match="fresh Stagehand"):
        await middleware.abefore_agent({}, MagicMock())


async def test_model_failure_closes_client(middleware):
    request = ModelRequest(model=MagicMock(), messages=[])
    with pytest.raises(RuntimeError, match="model failed"):
        await middleware.awrap_model_call(
            request, AsyncMock(side_effect=RuntimeError("model failed"))
        )
    middleware._facade.close.assert_awaited_once()


async def test_tool_failure_closes_client(middleware):
    with pytest.raises(RuntimeError, match="tool failed"):
        await middleware.awrap_tool_call(
            MagicMock(), AsyncMock(side_effect=RuntimeError("tool failed"))
        )
    middleware._facade.close.assert_awaited_once()
