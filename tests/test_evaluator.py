"""Tests for replay evaluator."""

from __future__ import annotations

import time

from stepdiff.eval.evaluator import FullStatePredictor, HeuristicPredictor, compare_runs, evaluate_run
from stepdiff.storage import EVAL_REPORT_FILE
from stepdiff.schemas import (
    BrowserAction,
    CompactObservation,
    StepRecord,
    StepState,
)


def _state(text: str) -> StepState:
    return StepState(
        url="file:///demo",
        title="Demo",
        screenshot_path=None,
        dom_text=text,
        dom_nodes=[],
        timestamp=time.time(),
    )


def _step(step_id: str, action: BrowserAction, run_id: str = "test_run") -> StepRecord:
    state = _state("page")
    return StepRecord(step_id=step_id, action=action, before=state, after=state, run_id=run_id)


def test_heuristic_predictor_validation_error() -> None:
    predictor = HeuristicPredictor()
    step = _step(
        "step_001",
        BrowserAction(type="click", selector="#submit-btn", value=None, description="submit"),
    )
    obs = CompactObservation(
        step_id="step_001",
        route="text_only",
        content="Validation error appeared: Email is required",
        crop_path=None,
        token_estimate=20,
        baseline_token_estimate=1200,
        confidence=0.95,
        savings_pct=98.0,
    )
    predicted = predictor.predict(obs, step)
    assert predicted.type == "click"
    assert predicted.selector == "#submit-btn"


def test_heuristic_predictor_modal() -> None:
    predictor = HeuristicPredictor()
    step = _step(
        "step_003",
        BrowserAction(type="click", selector="#checkout-btn", value=None, description="checkout"),
    )
    obs = CompactObservation(
        step_id="step_003",
        route="text_only",
        content="A modal or dialog appeared",
        crop_path=None,
        token_estimate=20,
        baseline_token_estimate=1200,
        confidence=0.85,
        savings_pct=98.0,
    )
    predicted = predictor.predict(obs, step)
    assert predicted.type == "click"
    assert predicted.selector == "#checkout-btn"


def test_evaluate_run_next_action_match(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("stepdiff.storage._project_root", lambda: tmp_path)
    monkeypatch.setattr("stepdiff.eval.evaluator.load_steps", lambda run_id: [
        _step(
            "step_001",
            BrowserAction(type="click", selector="#submit-btn", value=None, description="submit"),
            run_id,
        ),
        _step(
            "step_002",
            BrowserAction(type="type", selector="#email", value="a@b.com", description="email"),
            run_id,
        ),
    ])
    monkeypatch.setattr(
        "stepdiff.eval.evaluator.load_compact_observations",
        lambda run_id: [
            CompactObservation(
                step_id="step_001",
                route="text_only",
                content="Email is required",
                crop_path=None,
                token_estimate=10,
                baseline_token_estimate=100,
                confidence=0.95,
                savings_pct=90.0,
            )
        ],
    )
    monkeypatch.setattr(
        "stepdiff.eval.evaluator.load_run_meta",
        lambda run_id: type("Meta", (), {"task_description": "checkout"})(),
    )
    monkeypatch.setattr(
        "stepdiff.eval.evaluator.save_eval_report",
        lambda run_id, report, filename=EVAL_REPORT_FILE: tmp_path / filename,
    )

    report = evaluate_run("test_run", predictor="heuristic")
    assert report.total_steps == 1
    assert report.steps[0].action_match is False
    assert report.steps[0].predicted_action.type == "click"
    assert report.steps[0].recorded_action.type == "type"


def test_evaluate_run_single_step_has_no_predictions(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "stepdiff.eval.evaluator.load_steps",
        lambda run_id: [
            _step(
                "step_001",
                BrowserAction(type="click", selector="#submit-btn", value=None, description="submit"),
                run_id,
            ),
        ],
    )
    monkeypatch.setattr("stepdiff.eval.evaluator.load_compact_observations", lambda run_id: [])
    monkeypatch.setattr(
        "stepdiff.eval.evaluator.save_eval_report",
        lambda run_id, report, filename=EVAL_REPORT_FILE: tmp_path / filename,
    )

    report = evaluate_run("login_error", predictor="heuristic", save=True)
    assert report.total_steps == 0
    assert report.parity_score == 0.0


def test_full_state_predictor_token_estimate() -> None:
    predictor = FullStatePredictor()
    step = _step(
        "step_001",
        BrowserAction(type="click", selector="#btn", value=None, description="click"),
    )
    step.after.dom_text = "a" * 100
    assert predictor.estimate_tokens(step) == 25 + 800


def test_compare_runs_builds_report(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("stepdiff.eval.evaluator.evaluate_run", lambda run_id, predictor, **kwargs: type(
        "Report",
        (),
        {
            "parity_score": 0.9 if predictor == "claude" else 0.85,
            "total_compact_tokens": 100 if predictor == "claude" else 500,
            "steps": [
                type(
                    "StepResult",
                    (),
                    {
                        "step_id": "step_001",
                        "action_match": True,
                        "compact_tokens": 100 if predictor == "claude" else 500,
                    },
                )()
            ],
        },
    )())
    monkeypatch.setattr(
        "stepdiff.eval.evaluator.save_eval_comparison",
        lambda run_id, payload: tmp_path / "eval_comparison.json",
    )
    monkeypatch.setattr(
        "stepdiff.eval.evaluator.save_eval_summary",
        lambda run_id, content: tmp_path / "eval_summary.md",
    )

    comparison = compare_runs("test_run")
    assert comparison.compact_parity == 0.9
    assert comparison.baseline_parity == 0.85
    assert comparison.parity_preserved is True
    assert comparison.savings_pct == 80.0
    assert comparison.per_step[0]["compact_match"] is True
