# LangChain Stagehand

Add a persistent browser to a LangChain or Deep Agents agent with `StagehandMiddleware`. The middleware exposes Stagehand's shared `run`, `snapshot`, and `screenshot` tools, injects their browser instructions, and returns screenshots as model-visible images. No MCP server is needed.

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
from stagehand import Stagehand, browserbase


async def main():
    import os

    browser = await browserbase.launch(api_key=os.environ["BROWSERBASE_API_KEY"])
    stagehand = await Stagehand.create(browser=browser)
    agent = create_agent(
        "anthropic:claude-sonnet-4-6",
        middleware=[StagehandMiddleware(stagehand=stagehand)],
    )
    result = await agent.ainvoke({
        "messages": [{"role": "user", "content": "Open example.com and summarize the page."}]
    })
    print(result["messages"][-1].content)


asyncio.run(main())
```

Install the model integration separately, such as `pip install langchain-anthropic`, and set `ANTHROPIC_API_KEY` for this example. Browser tool calls use Stagehand's Playwright-shaped facade; they do not require a separate Stagehand model for these operations.

## Use with Deep Agents

Use the same Stagehand client setup and replace `create_agent` with:

```python
from deepagents import create_deep_agent

agent = create_deep_agent("anthropic:claude-sonnet-4-6", middleware=[StagehandMiddleware(stagehand=stagehand)])
```

Install `deepagents` separately. Use `ainvoke` or `astream`: browser tools and middleware are asynchronous.

## Client lifecycle

Pass a Stagehand client using `StagehandMiddleware(stagehand=stagehand)`. There is no middleware connection method or parallel configuration API. Use the Stagehand SDK directly to configure Browserbase or local Chrome:

```python
from stagehand import Stagehand, local_browser

browser = await local_browser.launch(headless=True)
stagehand = await Stagehand.create(browser=browser)
middleware = StagehandMiddleware(stagehand=stagehand)
```

Passing the client transfers cleanup responsibility to the middleware. It closes Stagehand and its browser after the agent finishes, and on model/tool exceptions or cancellation within those calls. Create a fresh client and middleware per agent invocation; reuse and concurrent invocations are rejected. Browser state is shared across tool calls within that invocation, not across invocations. Do not share the client with another agent. Take a new snapshot after navigation before using snapshot IDs.

If client creation fails before the middleware is constructed, close the browser yourself. Failures in other middleware hooks, graph-level interruption, or abandoning a stream may bypass these hooks; the application must ensure cleanup in those cases.

## Security and limitations

- Browser tools can navigate, submit forms, and interact with authenticated websites; use LangChain's human-in-the-loop middleware for sensitive actions
- Web page content is untrusted input, not instructions for your agent
- The Playwright-shaped API is not a general-purpose security sandbox or a substitute for network isolation
- `artifact_root` bounds where screenshots saved by run code can be written; use a dedicated directory per session
- Agent execution and session creation are asynchronous only; sessions are not checkpointed or resumed automatically

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
