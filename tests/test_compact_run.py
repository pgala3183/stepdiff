"""Tests for compact_run CLI script."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from compact_run import compact_run_folder, resolve_run_folder
from stepdiff.schemas import BrowserAction, StepRecord, StepState


@pytest.fixture
def project_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    backend = tmp_path / "backend"
    backend.mkdir()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("compact_run.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("stepdiff.storage._project_root", lambda: tmp_path)
    return tmp_path


def _write_step(
    run_folder: Path,
    run_id: str,
    step_id: str,
    *,
    before_text: str,
    after_text: str,
) -> None:
    ts = 1.0
    before = StepState(
        url="file:///test",
        title="Test",
        screenshot_path=None,
        dom_text=before_text,
        dom_nodes=[],
        timestamp=ts,
    )
    after = StepState(
        url="file:///test",
        title="Test",
        screenshot_path=None,
        dom_text=after_text,
        dom_nodes=[],
        timestamp=ts + 1,
    )
    action = BrowserAction(type="click", selector="#btn", value=None, description="click")
    record = StepRecord(step_id=step_id, action=action, before=before, after=after, run_id=run_id)
    jsonl = run_folder / "steps.jsonl"
    with jsonl.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json())
        handle.write("\n")


def test_resolve_run_folder(project_layout: Path) -> None:
    run_dir = project_layout / "runs" / "smoke"
    run_dir.mkdir(parents=True)
    folder, run_id = resolve_run_folder("runs/smoke")
    assert run_id == "smoke"
    assert folder == run_dir.resolve()


def test_resolve_run_folder_missing(project_layout: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_run_folder("runs/missing")


def test_compact_run_folder_human_output(project_layout: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = project_layout / "runs" / "smoke"
    run_dir.mkdir(parents=True)
    (run_dir / "steps").mkdir()
    _write_step(run_dir, "smoke", "step_001", before_text="Hello", after_text="Hello\nWorld")

    observations = compact_run_folder("runs/smoke", as_json=False)
    captured = capsys.readouterr()

    assert len(observations) == 1
    assert "step 1:" in captured.out
    assert "total: 1 step(s)" in captured.out


def test_compact_run_folder_json_output(project_layout: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = project_layout / "runs" / "smoke"
    run_dir.mkdir(parents=True)
    (run_dir / "steps").mkdir()
    _write_step(run_dir, "smoke", "step_001", before_text="A", after_text="B")

    compact_run_folder("runs/smoke", as_json=True)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["run_id"] == "smoke"
    assert payload["total_steps"] == 1
