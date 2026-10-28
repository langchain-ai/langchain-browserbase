"""Native LangChain middleware over Stagehand's shared browser facade."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal, TypeVar

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import ToolException, tool
from pydantic import Field
from stagehand import Stagehand
from stagehand_middleware.facade import (
    StagehandFacadeExecutionError,
    StagehandFacadeInputError,
    StagehandFacadeTools,
    facade_tools,
)

from .actions import SnapshotAction

T = TypeVar("T")


class StagehandMiddleware(AgentMiddleware):
    """Add browser tools with `middleware=[StagehandMiddleware(stagehand=client)]`."""

    def __init__(self, *, stagehand: Stagehand) -> None:
        self._stagehand = stagehand
        self._facade = self._open_facade()
        descriptions = {spec["name"]: spec["description"] for spec in facade_tools()}

        @tool(
            description=descriptions["run"]
            + (
                " Reuse the initialized browser; do not launch another browser or browser process."
                " Capture a new snapshot after navigation or stale IDs."
            )
        )
        async def run(
            *, code: str | None = None, actions: list[SnapshotAction] | None = None
        ) -> str:
            result = await self._call(lambda facade: facade.run(code=code, actions=actions))
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        @tool(
            description=descriptions["snapshot"]
            + (" Capture a new snapshot after navigation or stale IDs before taking actions.")
        )
        async def snapshot(*, includeIframes: bool = True) -> str:
            return await self._call(lambda facade: facade.snapshot(include_iframes=includeIframes))

        @tool(description=descriptions["screenshot"])
        async def screenshot(
            *,
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

    def _open_facade(self) -> StagehandFacadeTools:
        # The application owns the client and browser: `browser.close()` in run code
        # leaves both open and swaps in a fresh facade, so later calls still work.
        async def reopen() -> None:
            self._facade = self._open_facade()

        return StagehandFacadeTools(self._stagehand, on_close_requested=reopen)

    async def _call(self, operation: Callable[[StagehandFacadeTools], Awaitable[T]]) -> T:
        try:
            return await operation(self._facade)
        except (StagehandFacadeInputError, StagehandFacadeExecutionError) as error:
            raise ToolException(str(error)) from None
        except Exception as error:
            raise ToolException(f"{type(error).__name__}: {error}") from None
