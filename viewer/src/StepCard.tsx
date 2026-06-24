import { screenshotUrl } from "./api";
import { TokenBar } from "./TokenBar";
import "./StepCard.css";

interface StepCardProps {
  runId: string;
  stepNumber: number;
  step_id: string;
  actionDescription: string;
  compactObservation: string | null;
  route: "text_only" | "crop_with_context" | null;
  savings_pct: number | null;
  compact_tokens: number;
  baseline_tokens: number;
}

export function StepCard({
  runId,
  stepNumber,
  step_id,
  actionDescription,
  compactObservation,
  route,
  savings_pct,
  compact_tokens,
  baseline_tokens,
}: StepCardProps) {
  const routeClass =
    route === "crop_with_context" ? "step-card__badge--crop" : "step-card__badge--text";

  return (
    <article className="step-card">
      <header className="step-card__header">
        <div className="step-card__title">
          <span className="step-card__number">Step {stepNumber}</span>
          <span className="step-card__action">{actionDescription}</span>
        </div>
        {route ? (
          <span className={`step-card__badge ${routeClass}`}>{route}</span>
        ) : (
          <span className="step-card__badge step-card__badge--missing">no compact data</span>
        )}
      </header>

      <div className="step-card__screenshots">
        <figure className="step-card__shot">
          <figcaption>Before</figcaption>
          <img
            src={screenshotUrl(runId, step_id, "before")}
            alt={`${step_id} before`}
            loading="lazy"
          />
        </figure>
        <figure className="step-card__shot">
          <figcaption>After</figcaption>
          <img
            src={screenshotUrl(runId, step_id, "after")}
            alt={`${step_id} after`}
            loading="lazy"
          />
        </figure>
      </div>

      <div className="step-card__compact">
        <h4>Compact observation (LLM input)</h4>
        <pre>{compactObservation ?? "No compact observation — run compaction first."}</pre>
      </div>

      <div className="step-card__tokens">
        {savings_pct !== null && (
          <p className="step-card__savings-label">{savings_pct.toFixed(1)}% token savings</p>
        )}
        <TokenBar compact_tokens={compact_tokens} baseline_tokens={baseline_tokens} />
      </div>
    </article>
  );
}
