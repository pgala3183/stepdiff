"""Contract tests for all example run fixtures under examples/runs/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from stepdiff.compaction.codec import choose_route
from stepdiff.compaction.diff_dom import diff_dom_nodes, diff_dom_text
from stepdiff.compaction.routes import compact_step
from stepdiff.schemas import StepRecord

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_ROOT = PROJECT_ROOT / "examples" / "runs"


def _discover_fixtures() -> list[str]:
    if not EXAMPLES_ROOT.exists():
        return []
    names: list[str] = []
    for path in sorted(EXAMPLES_ROOT.iterdir()):
        if path.is_dir() and (path / "steps.jsonl").exists():
            names.append(path.name)
    return names


def _load_steps(fixture_dir: Path) -> list[StepRecord]:
    steps_path = fixture_dir / "steps.jsonl"
    steps: list[StepRecord] = []
    for line in steps_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            steps.append(StepRecord.model_validate_json(stripped))
    return steps


def _load_expected(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "expected.json"
    if not path.exists():
        pytest.skip(f"no expected.json in {fixture_dir.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_for_step(expected: dict[str, Any], step_id: str) -> dict[str, Any]:
    for step in expected.get("steps", []):
        if step.get("step_id") == step_id:
            return step
    raise KeyError(f"no expectations for {step_id}")


@pytest.fixture(params=_discover_fixtures())
def example_fixture(request: pytest.FixtureRequest) -> tuple[str, Path]:
    name: str = request.param
    return name, EXAMPLES_ROOT / name


def test_example_run_compact_contract(example_fixture: tuple[str, Path]) -> None:
    name, fixture_dir = example_fixture
    steps = _load_steps(fixture_dir)
    expected = _load_expected(fixture_dir)

    assert steps, f"{name}: steps.jsonl is empty"

    for step in steps:
        step_expected = _expected_for_step(expected, step.step_id)
        route = choose_route(step, fixture_dir)
        obs = compact_step(
            step.step_id,
            step.before,
            step.after,
            route,
            run_dir=fixture_dir,
        )

        assert route == step_expected["expected_route"], (
            f"{name}/{step.step_id}: route {route!r} != "
            f"{step_expected['expected_route']!r}"
        )

        content_lower = obs.content.lower()
        keywords = step_expected.get("content_contains_any", [])
        assert any(kw.lower() in content_lower for kw in keywords), (
            f"{name}/{step.step_id}: content missing any of {keywords!r}"
        )

        min_savings = step_expected.get("min_savings_pct", 0.5)
        assert obs.savings_pct >= min_savings, (
            f"{name}/{step.step_id}: savings {obs.savings_pct} < {min_savings}"
        )

        if step_expected.get("has_modal"):
            node_diff = diff_dom_nodes(step.before, step.after)
            assert node_diff.has_modal is True

        if step_expected.get("error_messages_cleared"):
            before_errors = diff_dom_text(step.before, step.after).error_messages
            assert not before_errors
