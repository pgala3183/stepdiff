import { useEffect, useState } from "react";
import { fetchRunList, type RunListItem } from "./api";
import { RunView } from "./RunView";
import "./App.css";

export default function App() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadRuns() {
      setLoading(true);
      setError(null);
      try {
        const items = await fetchRunList();
        if (cancelled) return;
        setRuns(items);
        if (items.length > 0) {
          setSelectedRunId((current) => current ?? items[0].run_id);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load runs");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadRuns();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="app">
      <header className="app__topbar">
        <h1 className="app__title">StepDiff</h1>
        <span className="app__run-id">{selectedRunId ?? "No run selected"}</span>
      </header>

      <div className="app__body">
        <aside className="app__sidebar">
          <h2 className="app__sidebar-title">Runs</h2>
          {loading && <p className="app__sidebar-status">Loading…</p>}
          {error && <p className="app__sidebar-status app__sidebar-status--error">{error}</p>}
          {!loading && !error && runs.length === 0 && (
            <p className="app__sidebar-status">No runs found.</p>
          )}
          <ul className="app__run-list">
            {runs.map((run) => (
              <li key={run.run_id}>
                <button
                  type="button"
                  className={`app__run-item${selectedRunId === run.run_id ? " app__run-item--active" : ""}`}
                  onClick={() => setSelectedRunId(run.run_id)}
                >
                  <span className="app__run-item-id">{run.run_id}</span>
                  <span className="app__run-item-count">{run.step_count} steps</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="app__main">
          {selectedRunId ? (
            <RunView runId={selectedRunId} />
          ) : (
            <div className="app__placeholder">Select a run to explore steps.</div>
          )}
        </main>
      </div>
    </div>
  );
}
