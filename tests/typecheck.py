"""Compile-time coverage of the public middleware API."""

from typing import assert_type

from stagehand import StagehandBrowser

from langchain_stagehand import StagehandMiddleware


def public_api(browser: StagehandBrowser) -> None:
    assert_type(StagehandMiddleware(browser=browser), StagehandMiddleware)
