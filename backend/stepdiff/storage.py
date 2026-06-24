"""Run folder I/O — persist and load captured browser runs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from stepdiff.schemas import (
    CompactObservation,
    RunEvalReport,
    RunMeta,
    StepRecord,
    StepState,
)

RUNS_DIR = "runs"
STEPS_DIR = "steps"
COMPACT_DIR = "compact"
RUN_META_FILE = "run.json"
STEPS_JSONL = "steps.jsonl"
EVAL_REPORT_FILE = "eval_report.json"
EVAL_BASELINE_REPORT_FILE = "eval_baseline_report.json"
EVAL_COMPARISON_FILE = "eval_comparison.json"
EVAL_SUMMARY_FILE = "eval_summary.md"


def project_root() -> Path:
    """Repository root (directory containing pyproject.toml and runs/)."""
    return Path(__file__).resolve().parents[2]


def _project_root() -> Path:
    return project_root()


def _run_path(run_id: str) -> Path:
    return _project_root() / RUNS_DIR / run_id


def run_folder_path(run_id: str) -> Path:
    return _run_path(run_id)


def get_run_folder(run_id: str) -> Path:
    folder = _run_path(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def reset_run_folder(run_id: str) -> Path:
    """Remove an existing run folder and recreate an empty one for a fresh recording."""
    folder = _run_path(run_id)
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    (folder / STEPS_DIR).mkdir()
    (folder / COMPACT_DIR).mkdir()
    (folder / "screenshots").mkdir()
    return folder


def load_run_meta(run_id: str) -> RunMeta:
    path = _run_path(run_id) / RUN_META_FILE
    return RunMeta.model_validate_json(path.read_text(encoding="utf-8"))


def load_steps(run_id: str) -> list[StepRecord]:
    path = _run_path(run_id) / STEPS_JSONL
    if not path.exists():
        return []

    steps: list[StepRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            steps.append(StepRecord.model_validate_json(stripped))
    return steps


def load_step_states(run_id: str, step_id: str) -> tuple[StepState, StepState]:
    steps_folder = _run_path(run_id) / STEPS_DIR
    before_path = steps_folder / f"{step_id}_before.json"
    after_path = steps_folder / f"{step_id}_after.json"
    before = StepState.model_validate_json(before_path.read_text(encoding="utf-8"))
    after = StepState.model_validate_json(after_path.read_text(encoding="utf-8"))
    return before, after


def save_compact_observation(run_id: str, obs: CompactObservation) -> Path:
    compact_folder = get_run_folder(run_id) / COMPACT_DIR
    compact_folder.mkdir(parents=True, exist_ok=True)
    path = compact_folder / f"{obs.step_id}.json"
    path.write_text(obs.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_compact_observations(run_id: str) -> list[CompactObservation]:
    compact_folder = _run_path(run_id) / COMPACT_DIR
    if not compact_folder.exists():
        return []

    observations: list[CompactObservation] = []
    for path in compact_folder.glob("*.json"):
        observations.append(
            CompactObservation.model_validate_json(path.read_text(encoding="utf-8"))
        )
    observations.sort(key=lambda obs: obs.step_id)
    return observations


def list_runs() -> list[str]:
    runs_root = _project_root() / RUNS_DIR
    if not runs_root.exists():
        return []
    return sorted(p.name for p in runs_root.iterdir() if p.is_dir())


def save_eval_report(
    run_id: str,
    report: RunEvalReport,
    filename: str = EVAL_REPORT_FILE,
) -> Path:
    path = get_run_folder(run_id) / filename
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_eval_report(run_id: str, filename: str = EVAL_REPORT_FILE) -> RunEvalReport | None:
    path = _run_path(run_id) / filename
    if not path.exists():
        return None
    return RunEvalReport.model_validate_json(path.read_text(encoding="utf-8"))


def save_eval_comparison(run_id: str, payload: dict) -> Path:
    path = get_run_folder(run_id) / EVAL_COMPARISON_FILE
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def save_eval_summary(run_id: str, content: str) -> Path:
    path = get_run_folder(run_id) / EVAL_SUMMARY_FILE
    path.write_text(content, encoding="utf-8")
    return path
