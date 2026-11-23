"use client";

import useSWR, { type SWRConfiguration } from "swr";

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? `HTTP ${status}`);
  }
}

function send(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-Requested-With", "invoiceflow"); // CSRF guard for cookie sessions
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  return fetch(path, { ...init, headers, credentials: "include" });
}

// Access tokens live 15 minutes; the httpOnly refresh cookie renews them. Concurrent 401s
// share a single refresh so the rotating refresh token is only used once.
let refreshing: Promise<boolean> | null = null;
export function refreshSession(): Promise<boolean> {
  refreshing ??= send("/api/auth/refresh", { method: "POST" })
    .then((r) => r.ok, () => false)
    .finally(() => { refreshing = null; });
  return refreshing;
}

const NO_REFRESH = ["/api/auth/login", "/api/auth/refresh", "/api/auth/logout"];

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res = await send(path, init);
  if (res.status === 401 && !NO_REFRESH.some((p) => path.startsWith(p))) {
    if (await refreshSession()) res = await send(path, init);
    if (res.status === 401) {
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = `/login?next=${next}`;
      }
      throw new ApiError(401, "Not authenticated");
    }
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data);
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body instanceof FormData ? body : JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

/** Saves a file the API returns (a template or an export) under `filename`. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  let res = await send(path, {});
  if (res.status === 401 && (await refreshSession())) res = await send(path, {});
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function useApi<T>(path: string | null, config?: SWRConfiguration<T>) {
  return useSWR<T>(path, (p: string) => request<T>(p), { revalidateOnFocus: false, ...config });
}

export function qs(params: Record<string, string | number | null | undefined>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") s.set(k, String(v));
  const out = s.toString();
  return out ? `?${out}` : "";
}
