"""Shared pytest fixtures for StepDiff tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from stepdiff.schemas import BrowserAction, StepRecord, StepState

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def make_step_state():
    def _make(dom_text: str, nodes: list[dict] | None = None) -> StepState:
        return StepState(
            url="http://localhost/",
            title="Test Page",
            screenshot_path=None,
            dom_text=dom_text,
            dom_nodes=nodes or [],
            timestamp=time.time(),
        )

    return _make


@pytest.fixture
def make_step_record(make_step_state):
    def _make(
        before_text: str,
        after_text: str,
        *,
        action_type: str = "click",
        selector: str | None = "#submit-btn",
        value: str | None = None,
        step_id: str = "step_001",
        run_id: str = "test_run",
        before_nodes: list[dict] | None = None,
        after_nodes: list[dict] | None = None,
    ) -> StepRecord:
        return StepRecord(
            step_id=step_id,
            action=BrowserAction(
                type=action_type,  # type: ignore[arg-type]
                selector=selector,
                value=value,
                description=f"{action_type} action",
            ),
            before=make_step_state(before_text, before_nodes),
            after=make_step_state(after_text, after_nodes),
            run_id=run_id,
        )

    return _make


@pytest.fixture
def tmp_run_folder(tmp_path: Path):
    run_dir = tmp_path / "runs" / "test_run"
    run_dir.mkdir(parents=True)
    (run_dir / "steps").mkdir()
    (run_dir / "screenshots").mkdir()
    yield run_dir
