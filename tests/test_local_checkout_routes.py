"""Verify local_checkout step routes match task expectations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stepdiff.compaction.codec import choose_route
from stepdiff.storage import load_steps, run_folder_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_PATH = PROJECT_ROOT / "tasks" / "local_checkout.json"
RUN_ID = "local_checkout"


@pytest.fixture
def local_checkout_steps() -> list:
    run_folder = run_folder_path(RUN_ID)
    if not run_folder.exists():
        pytest.skip(f"recorded run not found: runs/{RUN_ID}")
    steps = load_steps(RUN_ID)
    if len(steps) < 4:
        pytest.skip(f"runs/{RUN_ID} needs 4 steps — re-run record_demo")
    return steps


def test_local_checkout_step_routes_match_task(local_checkout_steps) -> None:
    expected = json.loads(TASK_PATH.read_text(encoding="utf-8"))["expected_routes"]
    run_folder = run_folder_path(RUN_ID)

    routes = [choose_route(step, run_folder) for step in local_checkout_steps]

    assert routes == expected, (
        f"routes {routes} != expected {expected}; "
        "re-record with: python scripts/record_demo.py --task tasks/local_checkout.json "
        f"--run-id {RUN_ID} --headless --compact"
    )
