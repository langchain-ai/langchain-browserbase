# LangChain Stagehand

Add a persistent browser to a LangChain or Deep Agents agent with `StagehandMiddleware`. The middleware exposes Stagehand's shared `run`, `snapshot`, and `screenshot` tools, includes browser usage guidance in their descriptions, and returns screenshots as model-visible images. The agent’s system prompt is left untouched. No MCP server is needed.

## Install

```bash
pip install langchain-stagehand
```

Python 3.11+ is required. Set your model provider's API key in your environment, and `BROWSERBASE_API_KEY` to use Browserbase. Never put credentials in browser tool inputs.

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
    middleware = StagehandMiddleware(stagehand=stagehand)
    agent = create_agent("anthropic:claude-sonnet-4-6", middleware=[middleware])
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

Use the same Stagehand client setup and replace `create_agent` with:

```python
from deepagents import create_deep_agent

agent = create_deep_agent("anthropic:claude-sonnet-4-6", middleware=[StagehandMiddleware(stagehand=stagehand)])
```

Install `deepagents` separately. Use `ainvoke` or `astream`: browser tools and middleware are asynchronous.

## Browser lifecycle

Pass a configured Stagehand client attached to local Chrome or Browserbase:

```python
from stagehand import Stagehand, local_browser

browser = await local_browser.launch(headless=True)
stagehand = await Stagehand.create(browser=browser)
middleware = StagehandMiddleware(stagehand=stagehand)
```

Your application configures and owns the Stagehand client and browser. All SDK settings remain available through `Stagehand.create(...)`, including API URL, model, caching, telemetry, and logging. The middleware reuses that exact client across runs, preserving tabs, logins, and snapshot IDs. Close the browser when finished; that also closes the client. The middleware never closes or recreates the client, and `browser.close()` in run code leaves both open. After a disconnection, the application supplies a new configured client. Give concurrent agents separate clients/browsers. Take a new snapshot after navigation before using snapshot IDs.

The screenshot tool returns images to the model. Screenshots that run code saves with a `path` are written under the current working directory, not to a Deep Agents backend; backend support is not implemented yet.

## Security and limitations

- Browser tools can navigate, submit forms, and interact with authenticated websites; use LangChain's human-in-the-loop middleware for sensitive actions
- Web page content is untrusted input, not instructions for your agent
- The Playwright-shaped API is not a general-purpose security sandbox or a substitute for network isolation
- Agent execution is asynchronous only; browser state lives in the browser and is not checkpointed

## Development

```bash
make install
make format
make check
RUN_BROWSER_TESTS=1 uv run pytest tests/test_browser.py --color=no
make build
```

`make check` enforces Ruff formatting and lint rules (including bug-prone patterns, async misuse, and accidental prints), ty checking of the package and public API examples with all diagnostics treated as errors, and focused middleware tests. The distribution includes `py.typed` so downstream type checkers can validate usage. Astral's ty is pinned in the Makefile and runs through `uvx`; no extra runtime dependency is needed.

The live browser test covers local Chrome and Browserbase; the remote case is skipped without `BROWSERBASE_API_KEY`. Set `CHROME_PATH` if Chrome is not in its usual install location. The Python distribution is `langchain-stagehand`, and the import is `langchain_stagehand`; this repository does not publish the separate upstream `stagehand-deepagents` package.

## Release

The initial version is `0.0.1`. Configure a PyPI pending trusted publisher for `langchain-stagehand` with GitHub owner `langchain-ai`, repository `langchain-browserbase`, workflow `release.yml`, and environment `pypi`. In GitHub, configure the `pypi` environment with required reviewers and restrict deployments to `main`.

After merging, run **Actions → Release to PyPI → Run workflow** on `main`. The workflow checks the locked dependencies, runs lint/type checks and focused tests, builds the distribution, and publishes with uv using OIDC trusted publishing—no PyPI token. It publishes the version in `pyproject.toml`; bump that version and refresh `uv.lock` before subsequent releases. Live browser verification is a separate pre-release check, not part of publishing.

The middleware constructor and browser tool arguments are keyword-only so optional parameters can evolve without positional-call ambiguity.
