"""Playwright browser control for recording and replaying actions."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, Page, Playwright, async_playwright

from stepdiff.browser.state import capture_state
from stepdiff.schemas import BrowserAction, RunMeta, StepRecord, StepState
from stepdiff.storage import project_root, reset_run_folder

STEPS_DIR = "steps"
SCREENSHOTS_DIR = "screenshots"
STEPS_JSONL = "steps.jsonl"
RUN_META_FILE = "run.json"


def _action_description(action_type: str, selector: str | None, value: str | None) -> str:
    match action_type:
        case "click":
            return f"Click {selector}"
        case "type":
            return f"Type {value!r} into {selector}"
        case "navigate":
            return f"Navigate to {value}"
        case "scroll":
            return "Scroll page down"
        case "wait":
            return f"Wait {value or '1'}s"
        case _:
            return action_type


def _parse_action(raw: dict[str, Any]) -> BrowserAction:
    action_type = raw["type"]
    selector = raw.get("selector")
    value = raw.get("value")

    if action_type == "wait":
        ms = raw.get("metadata", {}).get("ms")
        if ms is not None:
            value = str(float(ms) / 1000.0)
        elif value is None:
            value = "1"

    return BrowserAction(
        type=action_type,
        selector=selector,
        value=value,
        description=raw.get("description") or _action_description(action_type, selector, value),
    )


class BrowserController:
    """Local Playwright browser wrapper — no remote browser services."""

    def __init__(self, run_id: str, headless: bool = True) -> None:
        self.run_id = run_id
        self.headless = headless
        self.run_folder = reset_run_folder(run_id)
        self.steps_folder = self.run_folder / STEPS_DIR
        self.steps_jsonl_path = self.run_folder / STEPS_JSONL
        self.run_meta_path = self.run_folder / RUN_META_FILE

        self._start_time = time.time()
        self._run_meta = RunMeta(
            run_id=run_id,
            task_description="",
            start_time=self._start_time,
            step_count=0,
        )
        self._step_number = 0
        self._step_records: list[StepRecord] = []

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started — call start() first")
        return self._page

    async def start(self) -> Page:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._page = await self._browser.new_page()
        return self._page

    async def _wait_for_network_idle(self) -> None:
        if self._page is None:
            return
        try:
            await self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

    async def _execute_action(self, action: BrowserAction) -> None:
        page = self.page
        match action.type:
            case "navigate":
                if action.value:
                    await page.goto(action.value)
            case "click":
                if action.selector:
                    await page.click(action.selector)
            case "type":
                if action.selector and action.value is not None:
                    await page.fill(action.selector, action.value)
            case "scroll":
                await page.evaluate("window.scrollBy(0, 500)")
            case "wait":
                await asyncio.sleep(float(action.value or "1"))

    def _append_step_jsonl(self, record: StepRecord) -> None:
        with self.steps_jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json())
            handle.write("\n")

    def _save_state_json(self, step_id: str, phase: str, state: StepState) -> None:
        path = self.steps_folder / f"{step_id}_{phase}.json"
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

    async def execute_step(
        self,
        action: BrowserAction,
        task_description: str = "",
    ) -> StepRecord:
        if task_description and not self._run_meta.task_description:
            self._run_meta = self._run_meta.model_copy(update={"task_description": task_description})

        self._step_number += 1
        step_id = f"step_{self._step_number:03d}"

        before = await capture_state(
            self.page,
            self.run_folder,
            f"{step_id}_before.png",
        )
        await self._execute_action(action)
        await self._wait_for_network_idle()
        after = await capture_state(
            self.page,
            self.run_folder,
            f"{step_id}_after.png",
        )

        record = StepRecord(
            step_id=step_id,
            action=action,
            before=before,
            after=after,
            run_id=self.run_id,
        )

        self._append_step_jsonl(record)
        self._save_state_json(step_id, "before", before)
        self._save_state_json(step_id, "after", after)
        self._step_records.append(record)
        return record

    async def close(self) -> RunMeta:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        self._page = None
        self._browser = None
        self._playwright = None

        self._run_meta = self._run_meta.model_copy(
            update={
                "end_time": time.time(),
                "step_count": len(self._step_records),
            }
        )
        self.run_meta_path.write_text(self._run_meta.model_dump_json(indent=2), encoding="utf-8")
        return self._run_meta

    async def run_task(self, task: dict[str, Any]) -> list[StepRecord]:
        description = task.get("description", "")
        if description:
            self._run_meta = self._run_meta.model_copy(update={"task_description": description})

        if self._step_number == 0:
            html_path = task.get("html_path") or task.get("url")
            start_url = task.get("start_url")
            if html_path:
                path = Path(html_path)
                if not path.is_absolute():
                    path = project_root() / path
                if path.exists():
                    await self.page.goto(path.resolve().as_uri())
                elif str(html_path).startswith("http"):
                    await self.page.goto(str(html_path))
            elif start_url:
                await self.page.goto(start_url)
            await self._wait_for_network_idle()

        records: list[StepRecord] = []
        for raw_action in task.get("actions", []):
            action = _parse_action(raw_action)
            records.append(await self.execute_step(action, description))
        return records
