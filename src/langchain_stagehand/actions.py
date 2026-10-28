"""Typed snapshot actions accepted by Stagehand's browser facade."""

from typing import Literal, NotRequired

from typing_extensions import TypedDict


class ClickAction(TypedDict):
    op: Literal["click", "hover"]
    id: str


class FillAction(TypedDict):
    op: Literal["fill"]
    id: str
    value: str


class TypeAction(TypedDict):
    op: Literal["type"]
    id: str
    text: str
    delay: NotRequired[float]


class PressAction(TypedDict):
    op: Literal["press"]
    id: str
    key: str


class SelectAction(TypedDict):
    op: Literal["select"]
    id: str
    values: str | list[str]


SnapshotAction = ClickAction | FillAction | TypeAction | PressAction | SelectAction
