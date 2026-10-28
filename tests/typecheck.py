"""Compile-time coverage of the public middleware API."""

from typing import assert_type

from stagehand import Stagehand

from langchain_stagehand import StagehandMiddleware


def public_api(stagehand: Stagehand) -> None:
    assert_type(StagehandMiddleware(stagehand=stagehand), StagehandMiddleware)
