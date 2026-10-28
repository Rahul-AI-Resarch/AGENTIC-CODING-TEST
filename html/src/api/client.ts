import { API_BASE, API_PATHS } from "./paths";
import type { Health, Meta, OrchestraEvent, Run, RunFile } from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { error?: string };
      if (body?.error) message = body.error;
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>(API_PATHS.health),

  meta: () => request<Meta>(API_PATHS.meta),

  listRuns: (limit = 50) =>
    request<{ runs: Run[]; count: number }>(`${API_PATHS.runs}?limit=${limit}`),

  createRun: (input: {
    prompt: string;
    mode: string;
    title?: string;
    reference?: string;
  }) =>
    request<Run>(API_PATHS.runs, {
      method: "POST",
      body: JSON.stringify(input),
    }),

  getRun: (id: string) => request<Run>(API_PATHS.run(id)),

  deleteRun: (id: string) =>
    request<{ deleted: string }>(API_PATHS.run(id), { method: "DELETE" }),

  listFiles: (id: string) =>
    request<{ run_id: string; files: RunFile[]; count: number }>(
      API_PATHS.runFiles(id),
    ),

  getFile: (id: string, path: string) =>
    request<{ run_id: string; path: string; content: string }>(
      API_PATHS.runFile(id, path),
    ),
};

/**
 * Subscribe to the live event stream for a run.
 * Returns an unsubscribe function.
 */
export function subscribeToRun(
  id: string,
  onEvent: (event: OrchestraEvent) => void,
  onError?: (err: unknown) => void,
): () => void {
  const source = new EventSource(`${API_BASE}${API_PATHS.runEvents(id)}`);
  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as OrchestraEvent);
    } catch (err) {
      onError?.(err);
    }
  };
  source.onerror = (err) => onError?.(err);
  return () => source.close();
}
