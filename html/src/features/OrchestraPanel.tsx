import { useEffect, useRef } from "react";
import { Panel, Pill } from "../components/ui";
import type { OrchestraEvent } from "../api/types";

const KIND_TONE: Record<string, string> = {
  phase: "text-sky-400",
  card: "text-violet-400",
  pass: "text-acc-500",
  fail: "text-rose-400",
  gate_pass: "text-acc-500",
  gate_fail: "text-rose-400",
  tool: "text-amber-400",
  error: "text-rose-400",
};

function describe(event: OrchestraEvent): string {
  const d = event.data ?? {};
  const parts: string[] = [];
  for (const [key, value] of Object.entries(d)) {
    if (value === null || value === undefined) continue;
    if (typeof value === "object") {
      parts.push(`${key}=${JSON.stringify(value).slice(0, 160)}`);
    } else {
      parts.push(`${key}=${String(value).slice(0, 160)}`);
    }
  }
  return parts.join(" · ");
}

export function OrchestraPanel({
  events,
  connected,
}: {
  events: OrchestraEvent[];
  connected: boolean;
}) {
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events]);

  return (
    <Panel
      title="Orchestra"
      hint="live event stream"
      right={
        <Pill tone={connected ? "live" : "bad"}>
          {connected ? "● streaming" : "○ offline"}
        </Pill>
      }
    >
      <div
        ref={boxRef}
        className="h-64 overflow-y-auto rounded-lg border border-ink-700 bg-ink-950 p-2.5 font-mono text-[11.5px] leading-relaxed"
      >
        {events.length === 0 ? (
          <div className="text-mist-500">waiting for events…</div>
        ) : (
          events.map((event, i) => (
            <div key={i} className="flex gap-2 border-b border-ink-800 py-1 last:border-0">
              <span className="w-8 shrink-0 text-mist-500">
                {new Date((event.ts || 0) * 1000).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </span>
              <span
                className={`w-28 shrink-0 truncate ${KIND_TONE[event.kind] ?? "text-mist-400"}`}
              >
                {event.kind}
              </span>
              <span className="min-w-0 flex-1 break-words text-mist-200">
                {describe(event)}
              </span>
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}
