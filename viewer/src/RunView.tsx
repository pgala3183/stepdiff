import { useEffect, useMemo, useState } from "react";
import { fetchRun, fetchStep, type CompactObservation, type RunDetail } from "./api";
import { StepCard } from "./StepCard";
import "./RunView.css";

interface RunViewProps {
  runId: string;
}

interface StepViewData {
  step_id: string;
  stepNumber: number;
  actionDescription: string;
  compact: CompactObservation | null;
}

function stepNumberFromId(stepId: string, fallback: number): number {
  const match = /^step_(\d+)$/.exec(stepId);
  return match ? Number.parseInt(match[1], 10) : fallback;
}

export function RunView({ runId }: RunViewProps) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [steps, setSteps] = useState<StepViewData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const runDetail = await fetchRun(runId);
        if (cancelled) return;
        setRun(runDetail);

        const stepDetails = await Promise.all(
          runDetail.steps.map((summary, index) =>
            fetchStep(runId, summary.step_id).then((detail) => ({
              step_id: summary.step_id,
              stepNumber: stepNumberFromId(summary.step_id, index + 1),
              actionDescription: summary.description || summary.action.description,
              compact: detail.compact,
            })),
          ),
        );
        if (!cancelled) {
          setSteps(stepDetails);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load run");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const savingsSummary = useMemo(() => {
    const withCompact = steps.filter((step) => step.compact);
    const compactTotal = withCompact.reduce(
      (sum, step) => sum + (step.compact?.token_estimate ?? 0),
      0,
    );
    const baselineTotal = withCompact.reduce(
      (sum, step) => sum + (step.compact?.baseline_token_estimate ?? 0),
      0,
    );
    const savingsPct =
      baselineTotal > 0 ? (1 - compactTotal / baselineTotal) * 100 : 0;
    return { compactTotal, baselineTotal, savingsPct };
  }, [steps]);

  if (loading) {
    return <div className="run-view run-view--status">Loading run…</div>;
  }

  if (error) {
    return <div className="run-view run-view--status run-view--error">{error}</div>;
  }

  if (!run) {
    return <div className="run-view run-view--status">Run not found.</div>;
  }

  return (
    <div className="run-view">
      <section className="run-view__summary">
        <h2>{run.meta.task_description || "Untitled run"}</h2>
        <p className="run-view__meta">
          {run.meta.step_count} steps · runtime {run.meta.runtime}
        </p>
        <div className="run-view__savings">
          <div className="run-view__savings-stat">
            <span className="run-view__savings-label">Compact tokens</span>
            <strong>{savingsSummary.compactTotal}</strong>
          </div>
          <div className="run-view__savings-stat">
            <span className="run-view__savings-label">Baseline tokens</span>
            <strong>{savingsSummary.baselineTotal}</strong>
          </div>
          <div className="run-view__savings-stat run-view__savings-stat--highlight">
            <span className="run-view__savings-label">Overall savings</span>
            <strong>{savingsSummary.savingsPct.toFixed(1)}%</strong>
          </div>
        </div>
      </section>

      <div className="run-view__steps">
        {steps.map((step) => (
          <StepCard
            key={step.step_id}
            runId={runId}
            stepNumber={step.stepNumber}
            step_id={step.step_id}
            actionDescription={step.actionDescription}
            compactObservation={step.compact?.content ?? null}
            route={step.compact?.route ?? null}
            savings_pct={step.compact?.savings_pct ?? null}
            compact_tokens={step.compact?.token_estimate ?? 0}
            baseline_tokens={step.compact?.baseline_token_estimate ?? 0}
          />
        ))}
      </div>
    </div>
  );
}
