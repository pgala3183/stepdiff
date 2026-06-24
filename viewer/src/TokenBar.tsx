import "./TokenBar.css";

interface TokenBarProps {
  compact_tokens: number;
  baseline_tokens: number;
}

export function TokenBar({ compact_tokens, baseline_tokens }: TokenBarProps) {
  const max = Math.max(compact_tokens, baseline_tokens, 1);
  const compactWidth = (compact_tokens / max) * 100;
  const baselineWidth = (baseline_tokens / max) * 100;
  const savings =
    baseline_tokens > 0
      ? ((1 - compact_tokens / baseline_tokens) * 100).toFixed(1)
      : "0.0";

  return (
    <div className="token-bar">
      <div className="token-bar__row">
        <span className="token-bar__label">Compact</span>
        <div className="token-bar__track">
          <div
            className="token-bar__fill token-bar__fill--compact"
            style={{ width: `${compactWidth}%` }}
          />
        </div>
        <span className="token-bar__value">{compact_tokens}</span>
      </div>
      <div className="token-bar__row">
        <span className="token-bar__label">Baseline</span>
        <div className="token-bar__track">
          <div
            className="token-bar__fill token-bar__fill--baseline"
            style={{ width: `${baselineWidth}%` }}
          />
        </div>
        <span className="token-bar__value">{baseline_tokens}</span>
      </div>
      <p className="token-bar__savings">{savings}% saved vs baseline</p>
    </div>
  );
}
