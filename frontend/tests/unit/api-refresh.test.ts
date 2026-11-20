import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "@/lib/api";

type Reply = { status: number; body?: unknown };
const json = (r: Reply) => new Response(r.body === undefined ? "" : JSON.stringify(r.body), { status: r.status });

let calls: string[];
function serve(routes: Record<string, Reply[]>) {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (path: string) => {
    calls.push(path);
    const queue = routes[path];
    const next = queue && queue.length > 1 ? queue.shift()! : queue?.[0];
    return json(next ?? { status: 404 });
  }));
}

describe("api: short-lived sessions", () => {
  beforeEach(() => { vi.spyOn(console, "error").mockImplementation(() => {}); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("refreshes once on 401 and retries the request", async () => {
    serve({ "/api/invoices": [{ status: 401 }, { status: 200, body: { items: [1] } }], "/api/auth/refresh": [{ status: 200, body: {} }] });
    await expect(api.get("/api/invoices")).resolves.toEqual({ items: [1] });
    expect(calls).toEqual(["/api/invoices", "/api/auth/refresh", "/api/invoices"]);
  });

  it("shares one refresh between concurrent requests", async () => {
    serve({
      "/api/a": [{ status: 401 }, { status: 200, body: "a" }],
      "/api/b": [{ status: 401 }, { status: 200, body: "b" }],
      "/api/auth/refresh": [{ status: 200, body: {} }],
    });
    await expect(Promise.all([api.get("/api/a"), api.get("/api/b")])).resolves.toEqual(["a", "b"]);
    expect(calls.filter((c) => c === "/api/auth/refresh")).toHaveLength(1);
  });

  it("gives up with a 401 when the session cannot be refreshed", async () => {
    serve({ "/api/invoices": [{ status: 401 }], "/api/auth/refresh": [{ status: 401 }] });
    await expect(api.get("/api/invoices")).rejects.toMatchObject({ status: 401 });
    expect(calls).toEqual(["/api/invoices", "/api/auth/refresh"]);
  });

  it("does not try to refresh a failed login", async () => {
    serve({ "/api/auth/login": [{ status: 401, body: { detail: "Invalid email or password" } }] });
    await expect(api.post("/api/auth/login", {})).rejects.toBeInstanceOf(ApiError);
    expect(calls).toEqual(["/api/auth/login"]);
  });
});
