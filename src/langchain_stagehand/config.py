"""Typed options forwarded to the Stagehand SDK."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypedDict

from stagehand import BrowserbaseBrowserSettings, BrowserbaseRegion


class LocalBrowserOptions(TypedDict, total=False):
    """Local Chrome launch options."""

    headless: bool
    executable_path: str | Path
    chromium_sandbox: bool
    args: Sequence[str]
    user_data_dir: str | Path
    viewport_width: int
    viewport_height: int
    locale: str
    ignore_https_errors: bool


class BrowserbaseOptions(TypedDict, total=False):
    """Remote Browserbase launch options."""

    browser_settings: BrowserbaseBrowserSettings
    region: BrowserbaseRegion
    keep_alive: bool
    timeout: float
    extension_id: str


class StagehandOptions(TypedDict, total=False):
    """Stagehand session creation options."""

    api_key: str
    api_url: str
    model: str
    model_api_key: str
    model_headers: Mapping[str, str]
    system_prompt: str
    self_heal: bool
    dom_settle_timeout_ms: int
