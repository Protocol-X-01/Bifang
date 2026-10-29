from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class TodoItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    content: str = Field(min_length=1, max_length=1000)
    status: Literal["pending", "in_progress", "completed", "cancelled"]
    priority: Literal["high", "medium", "low"]


TODO_LIST = TypeAdapter(Annotated[list[TodoItem], Field(max_length=100)])


class TaskPlan:
    def __init__(self):
        self._items: list[TodoItem] = []
        self.revision = 0

    def replace(self, todos: list[dict]) -> dict:
        items = TODO_LIST.validate_python(todos, strict=True)
        if sum(item.status == "in_progress" for item in items) > 1:
            raise ValueError("Only one task may be in progress")
        self._items = items
        self.revision += 1
        return self.snapshot()

    def snapshot(self) -> dict:
        return {"revision": self.revision, "todos": [item.model_dump() for item in self._items]}
