import os

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from stagehand import browserbase, local_browser

from langchain_stagehand import StagehandMiddleware


@pytest.mark.skipif(not os.environ.get("RUN_BROWSER_TESTS"), reason="Opt-in live browser test")
@pytest.mark.parametrize("provider", ["local", "browserbase"])
async def test_live_browser(provider):
    if provider == "browserbase" and not os.environ.get("BROWSERBASE_API_KEY"):
        pytest.skip("BROWSERBASE_API_KEY is not configured")
    if provider == "local":
        browser = await local_browser.launch(
            headless=True, executable_path=os.environ.get("CHROME_PATH"), chromium_sandbox=False
        )
    else:
        browser = await browserbase.launch(api_key=os.environ["BROWSERBASE_API_KEY"])
    middleware = StagehandMiddleware(browser=browser)
    try:

        class ToolCallingModel(FakeMessagesListChatModel):
            def bind_tools(self, tools, **kwargs):
                return self

        model = ToolCallingModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "run",
                            "id": "navigate",
                            "args": {
                                "code": (
                                    'await page.goto("https://example.com"); '
                                    "return await page.title();"
                                )
                            },
                        }
                    ],
                ),
                AIMessage(
                    content="", tool_calls=[{"name": "snapshot", "id": "snapshot", "args": {}}]
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "screenshot",
                            "id": "screenshot",
                            "args": {"type": "jpeg", "quality": 40},
                        }
                    ],
                ),
                AIMessage(content="Done"),
                # A second run on the same browser still sees the page.
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "run", "id": "title", "args": {"code": "return page.url();"}}
                    ],
                ),
                AIMessage(content="Done again"),
            ]
        )
        agent = create_agent(model, middleware=[middleware])
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "Inspect example.com"}]}
        )
        outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
        assert outputs[0].content == "Example Domain"
        assert "Example Domain" in outputs[1].content
        assert outputs[2].content_blocks[0]["mime_type"] == "image/jpeg"
        result = await agent.ainvoke({"messages": [{"role": "user", "content": "Where are we?"}]})
        assert result["messages"][-2].content == "https://example.com/"
    finally:
        await middleware.aclose()
        await browser.close()
