"""Native LangChain middleware over Stagehand's shared browser facade."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Self

from jsonschema import Draft202012Validator
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langchain_core.tools import StructuredTool, ToolException
from stagehand import Stagehand, browserbase, local_browser
from stagehand_middleware.facade import (
    StagehandFacadeExecutionError,
    StagehandFacadeInputError,
    StagehandFacadeTools,
    facade_instructions,
    facade_tools,
)

from .config import BrowserbaseOptions, LocalBrowserOptions, StagehandOptions


class StagehandMiddleware(AgentMiddleware):
    """Expose one caller-owned Stagehand session to an asynchronous agent."""

    def __init__(self, stagehand: Stagehand, *, artifact_root: str | Path | None = None) -> None:
        self._facade = StagehandFacadeTools(stagehand, artifact_root=artifact_root)
        self.tools = [self._tool(spec) for spec in facade_tools()]

    def _tool(self, spec: dict[str, Any]) -> StructuredTool:
        name = spec["name"]
        validator = Draft202012Validator(spec["inputSchema"])

        async def invoke(**kwargs: Any) -> Any:
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

        return StructuredTool.from_function(
            coroutine=invoke,
            name=name,
            description=spec["description"],
            args_schema=spec["inputSchema"],
            handle_tool_error=True,
        )

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        blocks: list[str | dict[str, Any]] = (
            [dict(block) for block in request.system_message.content_blocks]
            if request.system_message
            else []
        )
        blocks.append({"type": "text", "text": facade_instructions()})
        system_message = (
            request.system_message.model_copy(update={"content": blocks})
            if request.system_message
            else SystemMessage(content=blocks)
        )
        return await handler(request.override(system_message=system_message))

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        *,
        provider: Literal["browserbase", "local"] = "browserbase",
        api_key: str | None = None,
        browserbase_options: BrowserbaseOptions | None = None,
        local_options: LocalBrowserOptions | None = None,
        stagehand_options: StagehandOptions | None = None,
        artifact_root: str | Path | None = None,
    ) -> AsyncIterator[Self]:
        """Launch a session and close it when the asynchronous context exits."""
        if provider == "browserbase":
            if local_options is not None:
                raise ValueError("local_options requires provider='local'")
            key = api_key or os.environ.get("BROWSERBASE_API_KEY")
            if not key:
                raise ValueError("Set BROWSERBASE_API_KEY or pass api_key for Browserbase.")
            browser = await browserbase.launch(api_key=key, **(browserbase_options or {}))
        elif provider == "local":
            if browserbase_options is not None or api_key is not None:
                raise ValueError("Browserbase options and api_key require provider='browserbase'")
            browser = await local_browser.launch(**(local_options or {}))
        else:
            raise ValueError("provider must be 'browserbase' or 'local'")
        try:
            stagehand = await Stagehand.create(browser=browser, **(stagehand_options or {}))
            try:
                yield cls(stagehand, artifact_root=artifact_root)
            finally:
                await stagehand.close()
        finally:
            await browser.close()
