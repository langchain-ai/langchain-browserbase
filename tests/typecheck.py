"""Compile-time coverage of the public configuration and middleware API."""

from typing import assert_type

from stagehand import Stagehand

from langchain_stagehand import (
    BrowserbaseOptions,
    LocalBrowserOptions,
    StagehandMiddleware,
    StagehandOptions,
)


async def public_api(stagehand: Stagehand) -> None:
    assert_type(StagehandMiddleware(stagehand), StagehandMiddleware)
    local: LocalBrowserOptions = {"headless": True}
    remote: BrowserbaseOptions = {"keep_alive": True}
    session: StagehandOptions = {"model": "openai/gpt-4.1"}
    async with StagehandMiddleware.connect(provider="local", local_options=local) as middleware:
        assert_type(middleware, StagehandMiddleware)
    async with StagehandMiddleware.connect(
        browserbase_options=remote, stagehand_options=session
    ) as middleware:
        assert_type(middleware, StagehandMiddleware)
