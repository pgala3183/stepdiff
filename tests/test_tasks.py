"""Validate task definition JSON files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = PROJECT_ROOT / "tasks"

REQUIRED_ACTION_FIELDS = {"type", "description"}


@pytest.fixture
def task_files() -> list[Path]:
    if not TASKS_DIR.exists():
        return []
    return sorted(TASKS_DIR.glob("*.json"))


@pytest.mark.parametrize(
    "task_path",
    sorted((PROJECT_ROOT / "tasks").glob("*.json"))
    if (PROJECT_ROOT / "tasks").exists()
    else [],
    ids=lambda p: p.stem,
)
def test_task_file_structure(task_path: Path) -> None:
    task = json.loads(task_path.read_text(encoding="utf-8"))

    assert "id" in task
    assert "description" in task
    assert "actions" in task
    assert isinstance(task["actions"], list)
    assert len(task["actions"]) >= 1

    for action in task["actions"]:
        assert REQUIRED_ACTION_FIELDS <= set(action.keys())
        assert action["type"] in ("click", "type", "navigate", "scroll", "wait")

    expected_routes = task.get("expected_routes")
    if expected_routes is not None:
        assert len(expected_routes) == len(task["actions"])
        for route in expected_routes:
            assert route in ("text_only", "crop_with_context")

    url = task.get("url") or task.get("html_path")
    if url and not str(url).startswith("http"):
        resolved = PROJECT_ROOT / url
        assert resolved.exists(), f"task page not found: {resolved}"
