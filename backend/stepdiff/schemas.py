"""StepDiff data contract — Pydantic v2 models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StepState(BaseModel):
    """Captured state of the page at one moment."""

    model_config = ConfigDict(from_attributes=True)

    url: str
    title: str
    screenshot_path: str | None = None
    dom_text: str
    dom_nodes: list[dict[str, Any]]
    timestamp: float


class BrowserAction(BaseModel):
    """One action the agent took."""

    model_config = ConfigDict(from_attributes=True)

    type: Literal["click", "type", "navigate", "scroll", "wait"]
    selector: str | None = None
    value: str | None = None
    description: str


class StepRecord(BaseModel):
    """Full before/after pair for one step."""

    model_config = ConfigDict(from_attributes=True)

    step_id: str
    action: BrowserAction
    before: StepState
    after: StepState
    run_id: str


class RunMeta(BaseModel):
    """Metadata about a whole session."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str
    task_description: str
    start_time: float
    end_time: float | None = None
    step_count: int
    runtime: Literal["local"] = "local"


class CompactObservation(BaseModel):
    """Compact representation sent to the LLM instead of a full screenshot."""

    model_config = ConfigDict(from_attributes=True)

    step_id: str
    route: Literal["text_only", "crop_with_context"]
    content: str
    crop_path: str | None = None
    token_estimate: int
    baseline_token_estimate: int
    confidence: float = Field(ge=0.0, le=1.0)
    savings_pct: float


class EvalResult(BaseModel):
    """Replay evaluator result for one step."""

    model_config = ConfigDict(from_attributes=True)

    step_id: str
    predicted_action: BrowserAction
    recorded_action: BrowserAction
    action_match: bool
    compact_tokens: int
    baseline_tokens: int


class RunEvalReport(BaseModel):
    """Full eval report for a run."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str
    steps: list[EvalResult]
    total_steps: int
    matching_steps: int
    parity_score: float
    total_compact_tokens: int
    total_baseline_tokens: int
    overall_savings_pct: float
