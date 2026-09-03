"""Typed contracts returned to programmatic clients."""

from pydantic import BaseModel, Field


class AssistantAnswer(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    needs_human: bool = False
    suggested_actions: list[str] = Field(default_factory=list, max_length=5)
