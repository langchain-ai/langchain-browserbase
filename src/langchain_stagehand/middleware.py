"""Native LangChain middleware over Stagehand's shared browser facade."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException, tool
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import Field
from stagehand import Stagehand
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
    """Give an agent a Stagehand client and close it when the agent finishes."""

    def __init__(self, *, stagehand: Stagehand, artifact_root: str | Path | None = None) -> None:
        self._facade = StagehandFacadeTools(stagehand, artifact_root=artifact_root)
        self._started = False
        self._finished = False
        descriptions = {spec["name"]: spec["description"] for spec in facade_tools()}

        @tool(
            description=descriptions["run"]
            + (
                " Reuse the initialized browser; do not launch another browser or browser process."
                " Capture a new snapshot after navigation or stale IDs."
            )
        )
        async def run(code: str | None = None, actions: list[SnapshotAction] | None = None) -> str:
            result = await self._call(self._facade.run(code=code, actions=actions))
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        @tool(
            description=descriptions["snapshot"]
            + (" Capture a new snapshot after navigation or stale IDs before taking actions.")
        )
        async def snapshot(includeIframes: bool = True) -> str:
            return await self._call(self._facade.snapshot(include_iframes=includeIframes))

        @tool(description=descriptions["screenshot"])
        async def screenshot(
            fullPage: bool | None = None,
            type: Literal["png", "jpeg"] = "png",
            quality: Annotated[float | None, Field(ge=0, le=100)] = None,
        ) -> list[dict[str, str]]:
            image = await self._call(
                self._facade.screenshot(
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

    @override
    async def abefore_agent(self, state: AgentState, runtime: Runtime) -> None:
        if self._started:
            raise RuntimeError(
                "Use a fresh Stagehand client and middleware for each agent invocation."
            )
        self._started = True

    @override
    async def aafter_agent(self, state: AgentState, runtime: Runtime) -> None:
        await self._close()

    async def _close(self) -> None:
        if not self._finished:
            self._finished = True
            await self._facade.close()

    async def _call(self, operation: Awaitable[T]) -> T:
        try:
            return await operation
        except (StagehandFacadeInputError, StagehandFacadeExecutionError) as error:
            raise ToolException(str(error)) from None

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        try:
            return await handler(request)
        except BaseException:
            await self._close()
            raise

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        try:
            return await handler(request)
        except BaseException:
            await self._close()
            raise
