# LangChain Stagehand

Add a persistent browser to a LangChain or Deep Agents agent with `StagehandMiddleware`. The middleware exposes Stagehand's shared `run`, `snapshot`, and `screenshot` tools, includes browser usage guidance in their descriptions, and returns screenshots as model-visible images. The agent’s system prompt is left untouched. No MCP server is needed.

## Install

This package is not published to PyPI yet. Install from a local checkout:

```bash
git clone https://github.com/langchain-ai/langchain-browserbase.git
pip install ./langchain-browserbase
```

Python 3.11+ is required. Set your model provider's API key and `BROWSERBASE_API_KEY` in your environment. Never put credentials in browser tool inputs.

## Use with LangChain

```python
import asyncio

from langchain.agents import create_agent
from langchain_stagehand import StagehandMiddleware
from stagehand import browserbase


async def main():
    import os

    browser = await browserbase.launch(api_key=os.environ["BROWSERBASE_API_KEY"])
    agent = create_agent(
        "anthropic:claude-sonnet-4-6",
        middleware=[StagehandMiddleware(browser=browser)],
    )
    try:
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": "Open example.com and summarize the page."}]
        })
        print(result["messages"][-1].content)
    finally:
        await browser.close()


asyncio.run(main())
```

Install the model integration separately, such as `pip install langchain-anthropic`, and set `ANTHROPIC_API_KEY` for this example. Browser tool calls use Stagehand's Playwright-shaped facade; they do not require a separate Stagehand model for these operations.

## Use with Deep Agents

Use the same browser setup and replace `create_agent` with:

```python
from deepagents import create_deep_agent

agent = create_deep_agent("anthropic:claude-sonnet-4-6", middleware=[StagehandMiddleware(browser=browser)])
```

Install `deepagents` separately. Use `ainvoke` or `astream`: browser tools and middleware are asynchronous.

## Browser lifecycle

Pass a browser launched with the Stagehand SDK, local Chrome or Browserbase:

```python
from stagehand import local_browser

browser = await local_browser.launch(headless=True)
middleware = StagehandMiddleware(browser=browser)
```

Your application owns the browser and closes it when it is done with the agent. The middleware attaches a Stagehand client on the first browser call and detaches it after each run, so the same agent can be invoked again and its tabs and logins carry over. If the connection fails, the next browser call attaches afresh. A browser serves one agent at a time: give concurrent agents their own browsers. Take a new snapshot after navigation before using snapshot IDs.

## Security and limitations

- Browser tools can navigate, submit forms, and interact with authenticated websites; use LangChain's human-in-the-loop middleware for sensitive actions
- Web page content is untrusted input, not instructions for your agent
- The Playwright-shaped API is not a general-purpose security sandbox or a substitute for network isolation
- `artifact_root` bounds where screenshots saved by run code can be written; use a dedicated directory per session
- Agent execution is asynchronous only; browser state lives in the browser and is not checkpointed

## Development

```bash
make install
make format
make check
RUN_BROWSER_TESTS=1 uv run pytest tests/test_browser.py --color=no
make build
```

`make check` enforces Ruff formatting and lint rules (including bug-prone patterns, async misuse, and accidental prints), ty checking of the package and public API examples with all diagnostics treated as errors, and focused agent/lifecycle tests. The distribution includes `py.typed` so downstream type checkers can validate usage. Astral's ty is pinned in the Makefile and runs through `uvx`; no extra runtime dependency is needed.

The live browser test covers local Chrome and Browserbase; the remote case is skipped without `BROWSERBASE_API_KEY`. Set `CHROME_PATH` if Chrome is not in its usual install location. The Python distribution is `langchain-stagehand`, and the import is `langchain_stagehand`; this repository does not publish the separate upstream `stagehand-deepagents` package.

Before release, configure package ownership and trusted publishing, run both live browser cases, and publish the built distribution to PyPI. CI and publishing workflows are not configured by this initial implementation.
