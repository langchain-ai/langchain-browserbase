import os

import pytest

from langchain_browserbase import BrowserbaseMiddleware


@pytest.mark.skipif(not os.environ.get("RUN_BROWSER_TESTS"), reason="Opt-in live browser test")
@pytest.mark.parametrize("provider", ["local", "browserbase"])
async def test_live_browser(provider):
    if provider == "browserbase" and not os.environ.get("BROWSERBASE_API_KEY"):
        pytest.skip("BROWSERBASE_API_KEY is not configured")
    options = {"headless": True} if provider == "local" else {}
    if provider == "local" and os.environ.get("CHROME_PATH"):
        options.update(executable_path=os.environ["CHROME_PATH"], chromium_sandbox=False)
    async with BrowserbaseMiddleware.connect(
        provider=provider, browser_options=options
    ) as middleware:
        run, snapshot, screenshot = middleware.tools
        result = await run.ainvoke(
            {"code": 'await page.goto("https://example.com"); return await page.title();'}
        )
        assert result == "Example Domain"
        assert "Example Domain" in await snapshot.ainvoke({})
        image = await screenshot.ainvoke({"type": "jpeg", "quality": 40})
        assert image[0]["mime_type"] == "image/jpeg"
        assert image[0]["base64"]
