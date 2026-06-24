#!/usr/bin/env python3
"""Record a StepDiff demo run."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from stepdiff.browser.controller import BrowserController
from stepdiff.compaction.codec import compact_run_id
from stepdiff.schemas import CompactObservation

PROJECT_ROOT = Path(__file__).parent.parent


def _project_root() -> Path:
    return PROJECT_ROOT


def _action_summary(action: dict[str, Any]) -> str:
    action_type = action.get("type", "unknown")
    selector = action.get("selector")
    value = action.get("value")

    match action_type:
        case "click":
            return f"click {selector}"
        case "type":
            return f"type {selector}"
        case "navigate":
            return f"navigate {value}"
        case "scroll":
            return "scroll"
        case "wait":
            return "wait"
        case _:
            return action_type


def _step_number(step_id: str, index: int) -> int:
    if step_id.startswith("step_") and step_id[5:].isdigit():
        return int(step_id[5:])
    return index + 1


def _savings_fraction(obs: CompactObservation) -> float:
    if obs.baseline_token_estimate <= 0:
        return 0.0
    return 1.0 - (obs.token_estimate / obs.baseline_token_estimate)


def load_task(path: Path) -> dict[str, Any]:
    task = json.loads(path.read_text(encoding="utf-8"))
    html_path = task.get("html_path")
    if html_path and not Path(html_path).is_absolute():
        resolved = _project_root() / html_path
        if resolved.exists():
            task["html_path"] = str(resolved)
    url = task.get("url")
    if url and not task.get("html_path") and not Path(url).is_absolute():
        resolved = _project_root() / url
        if resolved.exists():
            task["html_path"] = str(resolved)
    return task


def task_from_url(url: str, run_id: str) -> dict[str, Any]:
    path = Path(url)
    if not url.startswith("http") and path.exists():
        resolved = path if path.is_absolute() else _project_root() / path
        return {
            "id": run_id,
            "description": f"Open {resolved.name}",
            "html_path": str(resolved.resolve()),
            "actions": [],
        }
    return {
        "id": run_id,
        "description": f"Navigate to {url}",
        "start_url": url,
        "actions": [
            {
                "type": "navigate",
                "value": url,
                "description": f"Navigate to {url}",
            }
        ],
    }


def print_compact_summary(observations: list[CompactObservation]) -> None:
    total_compact = 0
    total_baseline = 0

    for index, obs in enumerate(observations):
        step_num = _step_number(obs.step_id, index)
        savings = _savings_fraction(obs)
        preview = obs.content[:60].replace("\n", " ")
        print(
            f"  step {step_num}: {obs.route}, {savings:.2%} saved, "
            f"confidence {obs.confidence:.2f} - {preview}"
        )
        total_compact += obs.token_estimate
        total_baseline += obs.baseline_token_estimate

    total_pct = 1.0 - (total_compact / total_baseline) if total_baseline else 0.0
    print(
        f"total: {len(observations)} step(s), {total_compact} compact tokens "
        f"vs {total_baseline} baseline, {total_pct:.2%} saved"
    )


async def record_run(
    task: dict[str, Any],
    *,
    run_id: str,
    headless: bool,
) -> tuple[list[str], int]:
    controller = BrowserController(run_id, headless=headless)
    await controller.start()
    try:
        records = await controller.run_task(task)
    finally:
        await controller.close()

    action_lines = [_action_summary(action) for action in task.get("actions", [])]
    if not action_lines and records:
        action_lines = [
            record.action.description or _action_summary(record.action.model_dump())
            for record in records
        ]

    return action_lines, len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a StepDiff browser run")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Single URL to navigate to")
    source.add_argument("--task", type=Path, help="Path to task JSON with multiple actions")
    parser.add_argument("--run-id", required=True, help="Run folder ID under runs/")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser headlessly (default: headed for demos)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        default=False,
        help="Compact the run immediately after recording",
    )
    parser.add_argument(
        "--runtime",
        choices=["local"],
        default="local",
        help="Browser runtime (local Playwright only)",
    )
    args = parser.parse_args()

    if args.runtime != "local":
        raise SystemExit("Only --runtime local is supported")

    run_id = args.run_id
    if args.task:
        task_path = args.task if args.task.is_absolute() else _project_root() / args.task
        if not task_path.exists():
            raise SystemExit(f"Task file not found: {task_path}")
        task = load_task(task_path)
    else:
        task = task_from_url(args.url, run_id)

    print(f"Recording run: {run_id}")
    action_lines, step_count = asyncio.run(
        record_run(task, run_id=run_id, headless=args.headless)
    )

    for index, line in enumerate(action_lines, start=1):
        print(f"  step {index}: {line} — done")

    print(f"Run saved to runs/{run_id}/ ({step_count} steps)")

    if args.compact:
        print("\nCompacting...")
        observations = compact_run_id(run_id)
        if observations:
            print_compact_summary(observations)
        else:
            print("  warning: no steps to compact", file=sys.stderr)


if __name__ == "__main__":
    main()
