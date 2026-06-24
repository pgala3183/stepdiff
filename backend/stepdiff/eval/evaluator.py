"""Replay evaluator — predicts next actions from compact observations."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from anthropic import Anthropic
from dotenv import load_dotenv

from stepdiff.schemas import (
    BrowserAction,
    CompactObservation,
    EvalResult,
    RunEvalReport,
    StepRecord,
)
from stepdiff.storage import (
    EVAL_BASELINE_REPORT_FILE,
    EVAL_REPORT_FILE,
    load_compact_observations,
    load_run_meta,
    load_steps,
    run_folder_path,
    save_eval_comparison,
    save_eval_report,
    save_eval_summary,
)

load_dotenv()

PredictorName = Literal["heuristic", "claude", "llm", "full_state"]
FULL_STATE_IMAGE_TOKENS = 800
FULL_STATE_DOM_CHARS = 3000


@dataclass
class ComparisonReport:
    run_id: str
    compact_parity: float
    baseline_parity: float
    compact_total_tokens: int
    baseline_total_tokens: int
    savings_pct: float
    parity_preserved: bool
    per_step: list[dict[str, Any]] = field(default_factory=list)


def _default_model() -> str:
    return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def _normalize_predictor(predictor: str) -> PredictorName:
    if predictor == "llm":
        return "claude"
    if predictor in ("heuristic", "claude", "full_state"):
        return predictor  # type: ignore[return-value]
    raise ValueError(f"Unknown predictor: {predictor}")


def _default_action(step: StepRecord) -> BrowserAction:
    return step.action.model_copy(deep=True)


def _parse_action_json(text: str) -> BrowserAction:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    data = json.loads(cleaned)
    action_type = data.get("type", "wait")
    if action_type not in ("click", "type", "navigate", "scroll", "wait"):
        action_type = "wait"
    return BrowserAction(
        type=action_type,
        selector=data.get("selector"),
        value=data.get("value"),
        description=str(data.get("description", "")),
    )


def _call_claude(
    client: Anthropic,
    model: str,
    content: str | list[dict[str, Any]],
) -> BrowserAction | None:
    try:
        message = client.messages.create(
            model=model,
            max_tokens=200,
            temperature=0,
            messages=[{"role": "user", "content": content}],
        )
        text_blocks = [block.text for block in message.content if block.type == "text"]
        return _parse_action_json("\n".join(text_blocks))
    except Exception:
        return None


class HeuristicPredictor:
    """Deterministic predictor for smoke tests — no API calls."""

    def predict(self, obs: CompactObservation, step: StepRecord) -> BrowserAction:
        content = obs.content.lower()

        if "error" in content or "required" in content:
            return BrowserAction(
                type="click",
                selector="#submit-btn",
                value=None,
                description="Retry submit after validation error",
            )

        if "modal" in content or "dialog" in content:
            return BrowserAction(
                type="click",
                selector="#checkout-btn",
                value=None,
                description="Open checkout modal",
            )

        if "field" in content or "input" in content:
            return BrowserAction(
                type="type",
                selector=step.action.selector or "#email",
                value=step.action.value,
                description="Fill input field",
            )

        return BrowserAction(
            type=step.action.type,
            selector=step.action.selector,
            value=step.action.value,
            description=f"Repeat current action type: {step.action.type}",
        )


class ClaudePredictor:
    """Claude-based next-action predictor using compact observations."""

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        api_key = os.getenv("ANTHROPIC_API_KEY")
        self._client = Anthropic(api_key=api_key) if api_key and api_key != "your_key_here" else None

    def _build_prompt(
        self,
        *,
        task_description: str,
        observation_text: str,
        step: StepRecord,
        full_context: list[StepRecord],
        context_label: str = "What just changed (compact observation)",
    ) -> str:
        previous_actions = [record.action.description for record in full_context]
        previous_text = "\n".join(f"- {desc}" for desc in previous_actions) or "- (none)"

        return f"""You are a browser automation agent. Based on the compact observation of what just changed on the page, predict the NEXT browser action to take to complete the task.

Task: {task_description}

{context_label}:
{observation_text}

Current URL: {step.after.url}
Interactive elements visible: {step.after.dom_text[:500]}

Previous actions taken:
{previous_text}

Respond with ONLY a JSON object like:
{{"type": "click|type|navigate|scroll", "selector": "CSS selector or null", "value": "text value or null", "description": "what you're doing and why"}}"""

    def predict(
        self,
        obs: CompactObservation,
        step: StepRecord,
        full_context: list[StepRecord],
        *,
        task_description: str = "",
    ) -> BrowserAction:
        if self._client is None:
            return _default_action(step)

        prompt = self._build_prompt(
            task_description=task_description,
            observation_text=obs.content,
            step=step,
            full_context=full_context,
        )
        predicted = _call_claude(self._client, self.model, prompt)
        return predicted if predicted is not None else _default_action(step)


class FullStatePredictor:
    """Expensive baseline predictor using full DOM text and screenshot vision."""

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        api_key = os.getenv("ANTHROPIC_API_KEY")
        self._client = Anthropic(api_key=api_key) if api_key and api_key != "your_key_here" else None

    def estimate_tokens(self, step: StepRecord) -> int:
        dom_text = step.after.dom_text[:FULL_STATE_DOM_CHARS]
        return len(dom_text) // 4 + FULL_STATE_IMAGE_TOKENS

    def _screenshot_base64(self, step: StepRecord, run_id: str) -> str | None:
        rel = step.after.screenshot_path
        if not rel:
            return None
        path = run_folder_path(run_id) / rel
        if not path.exists():
            return None
        return base64.standard_b64encode(path.read_bytes()).decode("ascii")

    def predict(
        self,
        step: StepRecord,
        full_context: list[StepRecord],
        *,
        task_description: str = "",
        run_id: str = "",
    ) -> BrowserAction:
        if self._client is None:
            return _default_action(step)

        dom_text = step.after.dom_text[:FULL_STATE_DOM_CHARS]
        claude = ClaudePredictor(model=self.model)
        claude._client = self._client
        prompt = claude._build_prompt(
            task_description=task_description,
            observation_text=dom_text,
            step=step,
            full_context=full_context,
            context_label="Full page state after the last action (DOM text)",
        )

        message_content: list[dict[str, Any]] = []
        image_b64 = self._screenshot_base64(step, run_id)
        if image_b64:
            message_content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_b64,
                    },
                }
            )
        message_content.append({"type": "text", "text": prompt})

        predicted = _call_claude(self._client, self.model, message_content)
        return predicted if predicted is not None else _default_action(step)


def _get_predictor(
    name: PredictorName,
) -> HeuristicPredictor | ClaudePredictor | FullStatePredictor:
    if name == "claude":
        return ClaudePredictor(model=_default_model())
    if name == "full_state":
        return FullStatePredictor(model=_default_model())
    return HeuristicPredictor()


def evaluate_run(
    run_id: str,
    predictor: PredictorName | str = "heuristic",
    *,
    report_filename: str = EVAL_REPORT_FILE,
    save: bool = True,
) -> RunEvalReport:
    predictor_name = _normalize_predictor(predictor)
    steps = load_steps(run_id)
    observations = load_compact_observations(run_id)
    observations_by_id = {obs.step_id: obs for obs in observations}

    task_description = ""
    try:
        task_description = load_run_meta(run_id).task_description
    except (FileNotFoundError, OSError):
        pass

    predictor_impl = _get_predictor(predictor_name)

    results: list[EvalResult] = []
    total_input_tokens = 0
    total_baseline_tokens = 0
    matching = 0

    for index in range(len(steps) - 1):
        step = steps[index]
        next_step = steps[index + 1]
        context = steps[: index + 1]

        if isinstance(predictor_impl, FullStatePredictor):
            predicted = predictor_impl.predict(
                step,
                context,
                task_description=task_description,
                run_id=run_id,
            )
            step_tokens = predictor_impl.estimate_tokens(step)
            step_baseline_tokens = step_tokens
        else:
            obs = observations_by_id.get(step.step_id)
            if obs is None:
                continue
            if isinstance(predictor_impl, ClaudePredictor):
                predicted = predictor_impl.predict(
                    obs,
                    step,
                    context,
                    task_description=task_description,
                )
            else:
                predicted = predictor_impl.predict(obs, step)
            step_tokens = obs.token_estimate
            step_baseline_tokens = obs.baseline_token_estimate

        actual_next = next_step.action
        action_match = predicted.type == actual_next.type
        if action_match:
            matching += 1

        total_input_tokens += step_tokens
        total_baseline_tokens += step_baseline_tokens

        results.append(
            EvalResult(
                step_id=step.step_id,
                predicted_action=predicted,
                recorded_action=actual_next,
                action_match=action_match,
                compact_tokens=step_tokens,
                baseline_tokens=step_baseline_tokens,
            )
        )

    total_steps = len(results)
    parity_score = matching / total_steps if total_steps else 0.0
    overall_savings = (
        round((1.0 - total_input_tokens / total_baseline_tokens) * 100.0, 2)
        if total_baseline_tokens
        else 0.0
    )

    report = RunEvalReport(
        run_id=run_id,
        steps=results,
        total_steps=total_steps,
        matching_steps=matching,
        parity_score=round(parity_score, 4),
        total_compact_tokens=total_input_tokens,
        total_baseline_tokens=total_baseline_tokens,
        overall_savings_pct=overall_savings,
    )
    if save:
        save_eval_report(run_id, report, filename=report_filename)
    return report


def _build_eval_summary(
    run_id: str,
    compact_parity: float,
    baseline_parity: float,
    compact_tokens: int,
    baseline_tokens: int,
    savings_pct: float,
    parity_preserved: bool,
) -> str:
    verdict = (
        "PASS — compact context preserved next-action parity"
        if parity_preserved
        else "REVIEW — some parity loss"
    )
    return (
        "# StepDiff eval summary\n"
        f"Run: {run_id}\n"
        f"Compact parity: {compact_parity:.0%} | Baseline parity: {baseline_parity:.0%}\n"
        f"Token savings: {savings_pct:.0%} ({compact_tokens} vs {baseline_tokens})\n"
        f"Verdict: {verdict}\n"
    )


def compare_runs(run_id: str) -> ComparisonReport:
    compact_report = evaluate_run(
        run_id,
        predictor="claude",
        report_filename=EVAL_REPORT_FILE,
    )
    baseline_report = evaluate_run(
        run_id,
        predictor="full_state",
        report_filename=EVAL_BASELINE_REPORT_FILE,
    )

    baseline_by_step = {result.step_id: result for result in baseline_report.steps}
    per_step: list[dict[str, Any]] = []

    for compact_result in compact_report.steps:
        baseline_result = baseline_by_step.get(compact_result.step_id)
        per_step.append(
            {
                "step_id": compact_result.step_id,
                "compact_match": compact_result.action_match,
                "baseline_match": baseline_result.action_match if baseline_result else False,
                "compact_tokens": compact_result.compact_tokens,
                "baseline_tokens": baseline_result.compact_tokens if baseline_result else 0,
            }
        )

    compact_total = compact_report.total_compact_tokens
    baseline_total = baseline_report.total_compact_tokens
    savings_pct = (
        round((1.0 - compact_total / baseline_total) * 100.0, 2) if baseline_total else 0.0
    )
    parity_preserved = compact_report.parity_score >= baseline_report.parity_score * 0.9

    comparison = ComparisonReport(
        run_id=run_id,
        compact_parity=compact_report.parity_score,
        baseline_parity=baseline_report.parity_score,
        compact_total_tokens=compact_total,
        baseline_total_tokens=baseline_total,
        savings_pct=savings_pct,
        parity_preserved=parity_preserved,
        per_step=per_step,
    )

    save_eval_comparison(run_id, asdict(comparison))
    save_eval_summary(
        run_id,
        _build_eval_summary(
            run_id,
            comparison.compact_parity,
            comparison.baseline_parity,
            comparison.compact_total_tokens,
            comparison.baseline_total_tokens,
            comparison.savings_pct / 100.0,
            comparison.parity_preserved,
        ),
    )
    return comparison
