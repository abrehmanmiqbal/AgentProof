"""Typed models used by AgentProof's regression-testing core."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssertionOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    EXISTS = "exists"


class AssertionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, description="Dot-separated path into the structured output.")
    operator: AssertionOperator
    expected: Any = None


class RegressionCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    input: dict[str, Any]
    assertions: list[AssertionSpec] = Field(min_length=1)


class AssertionResult(BaseModel):
    path: str
    operator: AssertionOperator
    passed: bool
    expected: Any = None
    actual: Any = None
    message: str


class RegressionResult(BaseModel):
    case_id: str
    passed: bool
    output: dict[str, Any] = Field(default_factory=dict)
    assertions: list[AssertionResult] = Field(default_factory=list)
    error: str | None = None
