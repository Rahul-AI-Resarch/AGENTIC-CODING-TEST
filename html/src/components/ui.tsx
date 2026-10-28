import type { ReactNode } from "react";

export function Panel({
  title,
  hint,
  right,
  children,
  className = "",
}: {
  title: string;
  hint?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`mb-4 rounded-xl border border-ink-700 bg-ink-800 p-4 ${className}`}
    >
      <header className="mb-3 flex items-center gap-3">
        <h2 className="text-[11px] font-semibold tracking-[0.14em] text-mist-400 uppercase">
          {title}
        </h2>
        {hint ? (
          <span className="text-[11px] text-mist-500">{hint}</span>
        ) : null}
        <div className="flex-1" />
        {right}
      </header>
      {children}
    </section>
  );
}

const STATUS_STYLES: Record<string, string> = {
  queued: "bg-ink-700 text-mist-400",
  running: "bg-amber-400/15 text-amber-400",
  paused: "bg-ink-700 text-mist-400",
  failed: "bg-rose-400/15 text-rose-400",
  done: "bg-acc-500/15 text-acc-500",
  cancelled: "bg-ink-700 text-mist-500",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded-md px-2 py-0.5 font-mono text-[10px] font-bold tracking-wide uppercase ${
        STATUS_STYLES[status] ?? "bg-ink-700 text-mist-400"
      }`}
    >
      {status}
    </span>
  );
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "bad" | "live";
}) {
  const tones = {
    neutral: "border-ink-700 text-mist-400",
    good: "border-acc-500/50 text-acc-500",
    bad: "border-rose-400/50 text-rose-400",
    live: "border-sky-400/50 text-sky-400",
  };
  return (
    <span
      className={`rounded-full border px-3 py-1 font-mono text-[11px] ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost";
  type?: "button" | "submit";
}) {
  const base =
    "rounded-lg px-4 py-2 text-[13px] font-bold transition disabled:cursor-not-allowed disabled:opacity-45";
  const styles =
    variant === "primary"
      ? "bg-acc-500 text-ink-950 hover:bg-acc-400"
      : "border border-ink-700 bg-ink-850 text-mist-400 hover:border-sky-400 hover:text-sky-400";
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${styles}`}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="mb-3 block">
      <span className="mb-1.5 block text-[11px] font-semibold tracking-[0.1em] text-mist-400 uppercase">
        {label}
      </span>
      {children}
      {hint ? (
        <span className="mt-1 block text-[11px] text-mist-500">{hint}</span>
      ) : null}
    </label>
  );
}
