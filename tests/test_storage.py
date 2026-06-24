"""Tests for run folder storage I/O."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from stepdiff.schemas import (
    BrowserAction,
    CompactObservation,
    RunEvalReport,
    RunMeta,
    StepRecord,
    StepState,
)
from stepdiff.storage import (
    get_run_folder,
    list_runs,
    load_compact_observations,
    load_run_meta,
    load_step_states,
    load_steps,
    reset_run_folder,
    save_compact_observation,
    save_eval_report,
)


@pytest.fixture
def run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(
        "stepdiff.storage._project_root",
        lambda: tmp_path,
    )
    rid = "test_run_001"
    folder = tmp_path / "runs" / rid
    folder.mkdir(parents=True)
    (folder / "steps").mkdir()
    meta = RunMeta(
        run_id=rid,
        task_description="test task",
        start_time=time.time(),
        step_count=1,
    )
    (folder / "run.json").write_text(meta.model_dump_json(), encoding="utf-8")
    return rid


def _sample_state() -> StepState:
    return StepState(
        url="http://localhost/",
        title="Test",
        screenshot_path="screenshots/step_001_before.png",
        dom_text="hello",
        dom_nodes=[],
        timestamp=time.time(),
    )


def test_load_run_meta(run_id: str) -> None:
    meta = load_run_meta(run_id)
    assert meta.run_id == run_id
    assert meta.task_description == "test task"


def test_load_and_save_steps_jsonl(run_id: str) -> None:
    action = BrowserAction(type="click", selector="#btn", value=None, description="click")
    state = _sample_state()
    record = StepRecord(
        step_id="step_001",
        action=action,
        before=state,
        after=state,
        run_id=run_id,
    )
    jsonl_path = get_run_folder(run_id) / "steps.jsonl"
    jsonl_path.write_text(record.model_dump_json() + "\n", encoding="utf-8")

    steps = load_steps(run_id)
    assert len(steps) == 1
    assert steps[0].step_id == "step_001"


def test_load_step_states(run_id: str) -> None:
    before = _sample_state()
    after = _sample_state()
    after.dom_text = "world"
    steps_dir = get_run_folder(run_id) / "steps"
    (steps_dir / "step_001_before.json").write_text(before.model_dump_json(), encoding="utf-8")
    (steps_dir / "step_001_after.json").write_text(after.model_dump_json(), encoding="utf-8")

    loaded_before, loaded_after = load_step_states(run_id, "step_001")
    assert loaded_before.dom_text == "hello"
    assert loaded_after.dom_text == "world"


def test_compact_observations_roundtrip(run_id: str) -> None:
    obs = CompactObservation(
        step_id="step_002",
        route="text_only",
        content="changed",
        crop_path=None,
        token_estimate=10,
        baseline_token_estimate=100,
        confidence=0.9,
        savings_pct=90.0,
    )
    path = save_compact_observation(run_id, obs)
    assert path.name == "step_002.json"

    loaded = load_compact_observations(run_id)
    assert len(loaded) == 1
    assert loaded[0].step_id == "step_002"


def test_list_runs_and_get_run_folder(run_id: str) -> None:
    assert run_id in list_runs()
    folder = get_run_folder(run_id)
    assert folder.is_dir()


def test_reset_run_folder_clears_previous_steps(run_id: str) -> None:
    steps_path = get_run_folder(run_id) / "steps.jsonl"
    steps_path.write_text('{"step_id":"step_001"}\n', encoding="utf-8")

    reset_run_folder(run_id)

    assert not steps_path.exists()
    assert (get_run_folder(run_id) / "steps").is_dir()
    assert (get_run_folder(run_id) / "screenshots").is_dir()


def test_save_eval_report(run_id: str) -> None:
    report = RunEvalReport(
        run_id=run_id,
        steps=[],
        total_steps=0,
        matching_steps=0,
        parity_score=0.0,
        total_compact_tokens=0,
        total_baseline_tokens=0,
        overall_savings_pct=0.0,
    )
    path = save_eval_report(run_id, report)
    assert path.name == "eval_report.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == run_id
