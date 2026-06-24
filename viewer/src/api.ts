export const BASE_URL = "http://localhost:8000";

export interface RunListItem {
  run_id: string;
  step_count: number;
}

export interface BrowserAction {
  type: string;
  selector: string | null;
  value: string | null;
  description: string;
}

export interface RunMeta {
  run_id: string;
  task_description: string;
  start_time: number;
  end_time: number | null;
  step_count: number;
  runtime: string;
}

export interface StepSummary {
  step_id: string;
  action: BrowserAction;
  description: string;
  url_before: string;
  url_after: string;
}

export interface RunDetail {
  meta: RunMeta;
  steps: StepSummary[];
}

export interface CompactObservation {
  step_id: string;
  route: "text_only" | "crop_with_context";
  content: string;
  crop_path: string | null;
  token_estimate: number;
  baseline_token_estimate: number;
  confidence: number;
  savings_pct: number;
}

export interface StepDetail {
  step: {
    step_id: string;
    action: BrowserAction;
    run_id: string;
  };
  compact: CompactObservation | null;
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${path}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchRuns(): Promise<string[]> {
  const items = await request<RunListItem[]>("/runs");
  return items.map((item) => item.run_id);
}

export async function fetchRunList(): Promise<RunListItem[]> {
  return request<RunListItem[]>("/runs");
}

export async function fetchRun(runId: string): Promise<RunDetail> {
  return request<RunDetail>(`/runs/${encodeURIComponent(runId)}`);
}

export async function fetchStep(runId: string, stepId: string): Promise<StepDetail> {
  return request<StepDetail>(
    `/runs/${encodeURIComponent(runId)}/steps/${encodeURIComponent(stepId)}`,
  );
}

export function screenshotUrl(
  runId: string,
  stepId: string,
  when: "before" | "after",
): string {
  return `${BASE_URL}/runs/${encodeURIComponent(runId)}/steps/${encodeURIComponent(stepId)}/screenshot/${when}`;
}
