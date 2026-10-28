"""Native LangChain middleware over Stagehand's shared browser facade."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool, ToolException
from langgraph.runtime import Runtime
from langgraph.types import Command
from stagehand import Stagehand
from stagehand_middleware.facade import (
    StagehandFacadeExecutionError,
    StagehandFacadeInputError,
    StagehandFacadeTools,
    facade_tools,
)
from typing_extensions import override


class StagehandMiddleware(AgentMiddleware):
    """Give an agent a Stagehand client and close it when the agent finishes."""

    def __init__(self, *, stagehand: Stagehand, artifact_root: str | Path | None = None) -> None:
        self._facade = StagehandFacadeTools(stagehand, artifact_root=artifact_root)
        self._started = False
        self._finished = False
        self.tools = [self._tool(spec) for spec in facade_tools()]

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

    def _tool(self, spec: dict[str, Any]) -> StructuredTool:
        name = spec["name"]
        validator = Draft202012Validator(spec["inputSchema"])

        async def invoke(**kwargs: Any) -> Any:
            if self._finished:
                raise ToolException("The Stagehand session has closed.")
            errors = list(validator.iter_errors(kwargs))
            if errors:
                raise ToolException(
                    "Invalid browser tool arguments; follow the tool's input schema."
                )
            try:
                if name == "run":
                    result = await self._facade.run(**kwargs)
                    return (
                        result
                        if isinstance(result, str)
                        else json.dumps(result, ensure_ascii=False)
                    )
                if name == "snapshot":
                    return await self._facade.snapshot(
                        include_iframes=kwargs.get("includeIframes", True)
                    )
                image = await self._facade.screenshot(
                    full_page=kwargs.get("fullPage"),
                    type=kwargs.get("type", "png"),
                    quality=kwargs.get("quality"),
                )
                return [{"type": "image", "base64": image["data"], "mime_type": image["mimeType"]}]
            except (StagehandFacadeInputError, StagehandFacadeExecutionError) as error:
                raise ToolException(str(error)) from None

        description = spec["description"]
        if name == "run":
            description += (
                " Reuse the initialized browser; do not launch another browser or browser process."
                " Snapshot action IDs are valid only for the latest snapshot;"
                " capture a new snapshot after navigation or stale IDs."
            )
        elif name == "snapshot":
            description += (
                " Capture a new snapshot after navigation or stale IDs before taking actions."
            )

        return StructuredTool.from_function(
            coroutine=invoke,
            name=name,
            description=description,
            args_schema=spec["inputSchema"],
            handle_tool_error=True,
        )

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
