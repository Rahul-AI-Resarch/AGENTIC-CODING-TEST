import { Panel } from "../components/ui";
import type { Meta } from "../api/types";

export function MetaPanel({ meta }: { meta: Meta | null }) {
  if (!meta) {
    return (
      <Panel title="Pipeline">
        <p className="text-[12.5px] text-mist-500">loading…</p>
      </Panel>
    );
  }

  return (
    <Panel title="Pipeline" hint="what the conductor will run">
      <ol className="mb-4 flex flex-wrap gap-1.5">
        {meta.pipeline.map((step, i) => (
          <li
            key={step}
            className="rounded-md border border-ink-700 bg-ink-850 px-2 py-1 font-mono text-[10.5px] text-mist-400"
          >
            <span className="text-mist-500">{i + 1}.</span> {step}
          </li>
        ))}
      </ol>

      <div className="mb-1 text-[11px] font-semibold tracking-[0.1em] text-mist-400 uppercase">
        Orchestra sections
      </div>
      <ul className="flex flex-wrap gap-1.5">
        {meta.orchestra.map((section) => (
          <li
            key={section}
            className="rounded-md border border-acc-500/25 bg-acc-500/5 px-2 py-1 font-mono text-[10.5px] text-acc-500"
          >
            {section}
          </li>
        ))}
      </ul>

      <div className="mt-4 grid grid-cols-3 gap-2">
        {[
          ["budget", `${meta.limits.run_max_seconds}s`],
          ["llm calls", String(meta.limits.run_max_llm_calls)],
          ["tokens", meta.limits.run_max_tokens.toLocaleString()],
        ].map(([label, value]) => (
          <div
            key={label}
            className="rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-center"
          >
            <b className="block font-mono text-[15px] text-mist-200">{value}</b>
            <i className="not-italic text-[10px] tracking-wide text-mist-500 uppercase">
              {label}
            </i>
          </div>
        ))}
      </div>
    </Panel>
  );
}
