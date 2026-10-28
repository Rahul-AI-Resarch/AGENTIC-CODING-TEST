import { useState } from "react";
import { Button, Field, Panel } from "../components/ui";
import type { ModeInfo, Run } from "../api/types";

export function IntakePanel({
  modes,
  onStart,
  busy,
}: {
  modes: ModeInfo[];
  onStart: (input: {
    prompt: string;
    mode: string;
    title?: string;
    reference?: string;
  }) => Promise<void>;
  busy: boolean;
}) {
  const [mode, setMode] = useState("website");
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const [reference, setReference] = useState("");

  const isGame = mode === "game";
  const active = modes.find((m) => m.id === mode);

  async function submit() {
    if (!prompt.trim()) return;
    await onStart({
      prompt: prompt.trim(),
      mode,
      title: title.trim() || undefined,
      reference: isGame ? reference.trim() || undefined : undefined,
    });
  }

  return (
    <Panel title="What do you want to build?" hint={active?.hint}>
      <div className="mb-3 flex gap-1.5">
        {modes.map((m) => (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            className={`rounded-lg border px-3 py-1.5 text-[12px] font-semibold transition ${
              mode === m.id
                ? "border-acc-500 bg-acc-500/10 text-acc-500"
                : "border-ink-700 bg-ink-850 text-mist-400 hover:border-ink-600"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <Field label="Prompt">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={5}
          placeholder={
            isGame
              ? "e.g. an arcade maze-chase game with pellets, four patrolling ghosts and a power-up that flips the chase for 6 seconds"
              : "e.g. a landing page for a coffee roastery with a menu, story section and contact form"
          }
          className="w-full resize-y rounded-lg border border-ink-700 bg-ink-850 p-3 font-mono text-[12.5px] text-mist-200 focus:border-sky-400 focus:outline-none"
        />
      </Field>

      {isGame ? (
        <Field
          label="Reference game"
          hint="The orchestra researches this on the web, captures screenshots, and builds a mechanics-faithful reimplementation with original art."
        >
          <input
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="pac-man"
            className="w-full rounded-lg border border-ink-700 bg-ink-850 p-2.5 font-mono text-[12.5px] text-mist-200 focus:border-sky-400 focus:outline-none"
          />
        </Field>
      ) : null}

      <Field label="Title (optional)">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="auto from prompt"
          className="w-full rounded-lg border border-ink-700 bg-ink-850 p-2.5 font-mono text-[12.5px] text-mist-200 focus:border-sky-400 focus:outline-none"
        />
      </Field>

      <Button onClick={submit} disabled={busy || !prompt.trim()}>
        {busy ? "Starting…" : "▶ Start build"}
      </Button>
    </Panel>
  );
}

export function RunsPanel({
  runs,
  activeId,
  onSelect,
}: {
  runs: Run[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Panel title="Builds" hint={`${runs.length} total`}>
      {runs.length === 0 ? (
        <p className="text-[12.5px] text-mist-500">
          No builds yet. Start one on the left.
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {runs.map((run) => (
            <li key={run.id}>
              <button
                onClick={() => onSelect(run.id)}
                className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition ${
                  activeId === run.id
                    ? "border-sky-400/60 bg-sky-400/5"
                    : "border-ink-700 bg-ink-850 hover:border-ink-600"
                }`}
              >
                <span className="w-16 shrink-0 font-mono text-[10px] text-mist-500 uppercase">
                  {run.mode}
                </span>
                <span className="min-w-0 flex-1 truncate text-[13px] text-mist-200">
                  {run.title}
                </span>
                <span className="shrink-0 font-mono text-[10.5px] text-mist-500">
                  {run.phase}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
