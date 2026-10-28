import { useCallback, useEffect, useState } from "react";
import { api, subscribeToRun } from "./api/client";
import type { Health, Meta, OrchestraEvent, Run } from "./api/types";
import { Pill } from "./components/ui";
import { IntakePanel, RunsPanel } from "./features/IntakePanel";
import { MetaPanel } from "./features/MetaPanel";
import { OrchestraPanel } from "./features/OrchestraPanel";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [events, setEvents] = useState<OrchestraEvent[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshRuns = useCallback(async () => {
    try {
      const { runs: list } = await api.listRuns();
      setRuns(list);
      return list;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return [];
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      try {
        const [h, m] = await Promise.all([api.health(), api.meta()]);
        if (cancelled) return;
        setHealth(h);
        setMeta(m);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
      await refreshRuns();
    }

    void boot();
    return () => {
      cancelled = true;
    };
  }, [refreshRuns]);

  // Poll health so the header pill reflects the live backend.
  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        setHealth(await api.health());
      } catch {
        setHealth(null);
      }
    }, 15000);
    return () => clearInterval(timer);
  }, []);

  // Subscribe to the live event stream for the selected run.
  useEffect(() => {
    if (!activeId) {
      setConnected(false);
      return;
    }
    setEvents([]);
    setConnected(true);
    const unsubscribe = subscribeToRun(
      activeId,
      (event) => setEvents((prev) => [...prev.slice(-500), event]),
      () => setConnected(false),
    );
    return () => {
      unsubscribe();
      setConnected(false);
    };
  }, [activeId]);

  async function startBuild(input: {
    prompt: string;
    mode: string;
    title?: string;
    reference?: string;
  }) {
    setBusy(true);
    setError(null);
    try {
      const run = await api.createRun(input);
      setActiveId(run.id);
      await refreshRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 flex items-center gap-4 border-b border-ink-700 bg-ink-900/95 px-6 py-3 backdrop-blur">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-acc-500 to-sky-400 font-extrabold text-ink-950">
          B
        </div>
        <h1 className="text-[16px] font-bold tracking-tight">
          Build Anything Agent
          <small className="ml-2.5 text-[11.5px] font-normal text-mist-500">
            web retrieval · real-time playtest · multi-file
          </small>
        </h1>
        <div className="flex-1" />
        {error ? (
          <span className="rounded-full border border-rose-400/50 px-3 py-1 font-mono text-[11px] text-rose-400">
            {error}
          </span>
        ) : null}
        <Pill tone={health ? "good" : "bad"}>
          {health ? `v${health.version} · online` : "api offline"}
        </Pill>
      </header>

      <main className="mx-auto grid max-w-[1500px] grid-cols-1 gap-5 p-5 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <div>
          <IntakePanel
            modes={meta?.modes ?? []}
            onStart={startBuild}
            busy={busy}
          />
          <RunsPanel
            runs={runs}
            activeId={activeId}
            onSelect={(id) => setActiveId(id)}
          />
        </div>
        <div>
          <OrchestraPanel events={events} connected={connected} />
          <MetaPanel meta={meta} />
        </div>
      </main>

      <footer className="px-6 py-6 text-center text-[11.5px] text-mist-500">
        BAA v3 · BYOK — your key stays in your browser/server memory and is never
        written to disk.
      </footer>
    </div>
  );
}
