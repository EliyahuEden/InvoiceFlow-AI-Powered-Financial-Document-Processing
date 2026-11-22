import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useLiveEvents } from "@/lib/events";
import { at } from "../support/at";

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("swr", () => ({ useSWRConfig: () => ({ mutate }) }));
vi.mock("@/lib/api", () => ({ api: { post: async () => ({ ticket: "test-ticket" }) } }));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

it("revalidates the queue and summary when another reviewer decides a case", async () => {
  let stream: EventTarget | undefined;
  vi.stubGlobal("EventSource", class extends EventTarget {
    constructor() { super(); stream = this; }
    close() { /* no remote stream */ }
  });
  renderHook(() => useLiveEvents());
  await waitFor(() => expect(stream).toBeDefined());
  stream?.dispatchEvent(new MessageEvent("exception.updated", { data: '{"status":"approved"}' }));
  await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));
  const match = at(mutate.mock.calls, 0)[0];
  expect(match("/api/review/queue?status=open")).toBe(true);
  expect(match("/api/review/summary")).toBe(true);
  expect(match("/api/suppliers")).toBe(false);
});
