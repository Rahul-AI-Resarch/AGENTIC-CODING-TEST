export type RunMode = "website" | "game";
export type RunStatus =
  | "queued"
  | "running"
  | "paused"
  | "failed"
  | "done"
  | "cancelled";

export interface Run {
  id: string;
  mode: RunMode;
  title: string;
  prompt: string;
  status: RunStatus;
  phase: string;
  slug: string;
  created_at: number;
  updated_at: number;
  metadata: Record<string, unknown>;
}

export interface Health {
  ok: boolean;
  app: string;
  version: string;
  tagline: string;
  time: number;
  subscribers: number;
}

export interface ModeInfo {
  id: RunMode;
  label: string;
  hint: string;
}

export interface Meta {
  app: string;
  version: string;
  tagline: string;
  modes: ModeInfo[];
  limits: {
    run_max_seconds: number;
    run_max_llm_calls: number;
    run_max_tokens: number;
  };
  pipeline: string[];
  orchestra: string[];
}

export interface RunFile {
  path: string;
  size: number;
}

export interface OrchestraEvent {
  kind: string;
  run_id: string | null;
  ts: number;
  data: Record<string, unknown>;
}
