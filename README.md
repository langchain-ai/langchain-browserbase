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


async def main():
    async with StagehandMiddleware.connect() as browser:
        agent = create_agent("anthropic:claude-sonnet-4-6", middleware=[browser])
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": "Open example.com and summarize the page."}]
        })
        print(result["messages"][-1].content)


asyncio.run(main())
```

Install the model integration separately, such as `pip install langchain-anthropic`, and set `ANTHROPIC_API_KEY` for this example. Browser tool calls use Stagehand's Playwright-shaped facade; they do not require a separate Stagehand model for these operations.

## Use with Deep Agents

Inside the same asynchronous context, replace `create_agent` with:

```python
from deepagents import create_deep_agent

agent = create_deep_agent("anthropic:claude-sonnet-4-6", middleware=[browser])
```

Install `deepagents` separately. Use `ainvoke` or `astream`: browser tools and middleware are asynchronous.

## Local browser and session options

```python
async with StagehandMiddleware.connect(
    provider="local",
    local_options={"headless": True},
) as browser:
    ...
```

Local mode requires Chrome. `local_options`, `browserbase_options`, and `stagehand_options` are typed dictionaries exported as `LocalBrowserOptions`, `BrowserbaseOptions`, and `StagehandOptions`. They expose common SDK settings with editor completion and static checking rather than untyped keyword bags. For example, pass Browserbase `region` or `browser_settings` in `browserbase_options`. Options for the wrong provider raise an error. For SDK settings not exposed here, create a Stagehand session yourself and pass it to the middleware constructor. The context manager closes both Stagehand and the browser on exit, including when the agent fails.

To reuse an existing Stagehand session, construct `StagehandMiddleware(stagehand)`. You own its lifecycle and must close it yourself. A browser session persists across agent calls while its context remains open. Do not share one middleware instance across unrelated conversations or tenants; the underlying facade serializes tool calls, but it does not isolate their browsing state. Take a new snapshot after navigation before using snapshot IDs.

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
