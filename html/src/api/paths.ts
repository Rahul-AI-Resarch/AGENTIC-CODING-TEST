/**
 * The API contract, client side.
 *
 * Every backend path the console uses lives here. `tests/test_contract.py`
 * parses this file and checks each path against `api/routes_table.py` on the
 * Python side, so a route rename can never silently break the UI.
 */
export const API_PATHS = {
  health: "/api/health",
  meta: "/api/meta",
  runs: "/api/runs",
  run: (id: string) => `/api/runs/${id}`,
  runEvents: (id: string) => `/api/runs/${id}/events`,
  runFiles: (id: string) => `/api/runs/${id}/files`,
  runFile: (id: string, path: string) => `/api/runs/${id}/files/${path}`,
} as const;

/** Base URL for the API. Empty = same origin (console served by FastAPI). */
export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
