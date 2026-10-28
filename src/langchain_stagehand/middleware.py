"""Native LangChain middleware over Stagehand's shared browser facade."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Literal, TypeVar

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.tools import ToolException, tool
from langgraph.runtime import Runtime
from pydantic import Field
from stagehand import Stagehand, StagehandBrowser
from stagehand_middleware.facade import (
    StagehandFacadeExecutionError,
    StagehandFacadeInputError,
    StagehandFacadeTools,
    facade_tools,
)
from typing_extensions import override

from .actions import SnapshotAction

T = TypeVar("T")


class StagehandMiddleware(AgentMiddleware):
    """Give an agent Stagehand's tools on a browser that the application owns.

    A Stagehand client attaches on the first browser call and detaches after each run,
    so the browser, its tabs and logins carry over to the next run. Close the browser
    yourself when you are done with the agent.
    """

    def __init__(
        self, *, browser: StagehandBrowser, artifact_root: str | Path | None = None
    ) -> None:
        self._browser = browser
        self._artifact_root = artifact_root
        self._facade: StagehandFacadeTools | None = None
        self._lock = asyncio.Lock()
        descriptions = {spec["name"]: spec["description"] for spec in facade_tools()}

        @tool(
            description=descriptions["run"]
            + (
                " Reuse the initialized browser; do not launch another browser or browser process."
                " Capture a new snapshot after navigation or stale IDs."
            )
        )
        async def run(code: str | None = None, actions: list[SnapshotAction] | None = None) -> str:
            result = await self._call(lambda facade: facade.run(code=code, actions=actions))
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        @tool(
            description=descriptions["snapshot"]
            + (" Capture a new snapshot after navigation or stale IDs before taking actions.")
        )
        async def snapshot(includeIframes: bool = True) -> str:
            return await self._call(lambda facade: facade.snapshot(include_iframes=includeIframes))

        @tool(description=descriptions["screenshot"])
        async def screenshot(
            fullPage: bool | None = None,
            type: Literal["png", "jpeg"] = "png",
            quality: Annotated[float | None, Field(ge=0, le=100)] = None,
        ) -> list[dict[str, str]]:
            image = await self._call(
                lambda facade: facade.screenshot(
                    full_page=fullPage,
                    type=type,
                    quality=quality,
                )
            )
            return [{"type": "image", "base64": image["data"], "mime_type": image["mimeType"]}]

        self.tools = [run, snapshot, screenshot]
        for browser_tool in self.tools:
            browser_tool.handle_tool_error = True
            browser_tool.handle_validation_error = True

    async def _attached(self) -> StagehandFacadeTools:
        if self._facade is None:
            stagehand = await Stagehand.create(browser=self._browser)
            # Run code's `browser.close()` detaches the client; the browser stays.
            self._facade = StagehandFacadeTools(
                stagehand, artifact_root=self._artifact_root, on_close_requested=stagehand.close
            )
        return self._facade

    async def _detach(self) -> None:
        if facade := self._facade:
            self._facade = None
            with contextlib.suppress(Exception):
                await facade.close()

    @override
    async def aafter_agent(self, state: AgentState, runtime: Runtime) -> None:
        async with self._lock:
            await self._detach()

    async def _call(self, operation: Callable[[StagehandFacadeTools], Awaitable[T]]) -> T:
        async with self._lock:
            try:
                return await operation(await self._attached())
            except (StagehandFacadeInputError, StagehandFacadeExecutionError) as error:
                raise ToolException(str(error)) from None
            except Exception as error:
                # The connection may be dead: detach so the next call attaches afresh.
                await self._detach()
                raise ToolException(f"{type(error).__name__}: {error}") from None
