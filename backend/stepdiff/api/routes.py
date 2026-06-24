"""FastAPI routes for StepDiff."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from stepdiff.browser.controller import BrowserController
from stepdiff.compaction.codec import choose_route, compact_step
from stepdiff.compaction.routes import CompactionRoute
from stepdiff.eval.evaluator import compare_runs, evaluate_run
from stepdiff.schemas import (
    BrowserAction,
    CompactObservation,
    RunEvalReport,
    RunMeta,
    StepRecord,
)
from stepdiff.storage import (
    get_run_folder,
    list_runs,
    load_compact_observations,
    load_run_meta,
    load_steps,
    project_root,
    run_folder_path,
    save_compact_observation,
)

router = APIRouter(tags=["stepdiff"])


def _require_run(run_id: str) -> None:
    if run_id not in list_runs():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


def _load_task(task_file: str) -> dict[str, Any]:
    path = Path(task_file)
    if not path.is_absolute():
        path = project_root() / path
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Task file not found: {task_file}")
    return json.loads(path.read_text(encoding="utf-8"))


async def _record_run(task_file: str, run_id: str, headless: bool) -> None:
    path = Path(task_file)
    if not path.is_absolute():
        path = project_root() / path
    task = json.loads(path.read_text(encoding="utf-8"))
    controller = BrowserController(run_id, headless=headless)
    await controller.start()
    try:
        await controller.run_task(task)
    finally:
        await controller.close()


def _run_recording_task(task_file: str, run_id: str, headless: bool) -> None:
    asyncio.run(_record_run(task_file, run_id, headless))


def _compact_run(run_id: str) -> list[CompactObservation]:
    steps = load_steps(run_id)
    run_folder = run_folder_path(run_id)
    observations: list[CompactObservation] = []
    for step in steps:
        route = choose_route(step, run_folder)
        obs = compact_step(
            step.step_id,
            step.before,
            step.after,
            route,
            run_dir=run_folder,
        )
        observations.append(obs)
        save_compact_observation(run_id, obs)
    return observations


class RecordRunRequest(BaseModel):
    task_file: str = "tasks/local_checkout.json"
    run_id: str
    headless: bool = True


class RecordRunResponse(BaseModel):
    run_id: str
    step_count: int
    run_folder: str


class RunListItem(BaseModel):
    run_id: str
    step_count: int


class StepSummary(BaseModel):
    step_id: str
    action: BrowserAction
    description: str
    url_before: str
    url_after: str


class RunDetailResponse(BaseModel):
    meta: RunMeta
    steps: list[StepSummary]


class EvalRequest(BaseModel):
    predictor: str = "heuristic"
    compare: bool = False


class StepDetailResponse(BaseModel):
    step: StepRecord
    compact: CompactObservation | None = None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/runs/record", response_model=RecordRunResponse)
def record_run(body: RecordRunRequest, background_tasks: BackgroundTasks) -> RecordRunResponse:
    if body.run_id in list_runs():
        raise HTTPException(status_code=409, detail=f"Run already exists: {body.run_id}")

    task = _load_task(body.task_file)
    run_folder = get_run_folder(body.run_id)
    background_tasks.add_task(_run_recording_task, body.task_file, body.run_id, body.headless)

    return RecordRunResponse(
        run_id=body.run_id,
        step_count=len(task.get("actions", [])),
        run_folder=str(run_folder),
    )


@router.post("/runs/{run_id}/compact", response_model=list[CompactObservation])
def compact_run_endpoint(run_id: str) -> list[CompactObservation]:
    _require_run(run_id)
    steps = load_steps(run_id)
    if not steps:
        raise HTTPException(status_code=400, detail="Run has no recorded steps")
    return _compact_run(run_id)


@router.post("/runs/{run_id}/eval", response_model=RunEvalReport)
def eval_run_endpoint(run_id: str, body: EvalRequest) -> RunEvalReport:
    _require_run(run_id)
    if body.predictor not in ("heuristic", "claude", "llm"):
        raise HTTPException(
            status_code=400,
            detail="predictor must be 'heuristic' or 'llm'",
        )

    steps = load_steps(run_id)
    if not steps:
        raise HTTPException(status_code=400, detail="Run has no recorded steps")

    observations = load_compact_observations(run_id)
    if not observations:
        _compact_run(run_id)

    if body.compare:
        compare_runs(run_id)

    predictor = "claude" if body.predictor == "llm" else body.predictor
    return evaluate_run(run_id, predictor=predictor)  # type: ignore[arg-type]


@router.get("/runs", response_model=list[RunListItem])
def get_runs() -> list[RunListItem]:
    items: list[RunListItem] = []
    for run_id in list_runs():
        step_count = 0
        try:
            step_count = load_run_meta(run_id).step_count
        except (FileNotFoundError, OSError):
            step_count = len(load_steps(run_id))
        items.append(RunListItem(run_id=run_id, step_count=step_count))
    return items


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: str) -> RunDetailResponse:
    _require_run(run_id)
    try:
        meta = load_run_meta(run_id)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=404, detail="Run metadata not found") from exc

    summaries = [
        StepSummary(
            step_id=step.step_id,
            action=step.action,
            description=step.action.description,
            url_before=step.before.url,
            url_after=step.after.url,
        )
        for step in load_steps(run_id)
    ]
    return RunDetailResponse(meta=meta, steps=summaries)


@router.get("/runs/{run_id}/steps/{step_id}", response_model=StepDetailResponse)
def get_step(run_id: str, step_id: str) -> StepDetailResponse:
    _require_run(run_id)
    steps = load_steps(run_id)
    step = next((item for item in steps if item.step_id == step_id), None)
    if step is None:
        raise HTTPException(status_code=404, detail=f"Step not found: {step_id}")

    observations = {obs.step_id: obs for obs in load_compact_observations(run_id)}
    return StepDetailResponse(step=step, compact=observations.get(step_id))


@router.get("/runs/{run_id}/steps/{step_id}/screenshot/{when}")
def get_step_screenshot(
    run_id: str,
    step_id: str,
    when: Literal["before", "after"],
) -> FileResponse:
    _require_run(run_id)
    steps = load_steps(run_id)
    step = next((item for item in steps if item.step_id == step_id), None)
    if step is None:
        raise HTTPException(status_code=404, detail=f"Step not found: {step_id}")

    state = step.before if when == "before" else step.after
    if not state.screenshot_path:
        raise HTTPException(status_code=404, detail=f"No {when} screenshot for step {step_id}")

    image_path = run_folder_path(run_id) / state.screenshot_path
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Screenshot file not found: {image_path.name}")

    return FileResponse(path=image_path, media_type="image/png", filename=image_path.name)
