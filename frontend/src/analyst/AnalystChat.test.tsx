import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { AnalystChat } from "./AnalystChat";

const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
class Stream {
  static instances: Stream[] = [];
  listeners = new Map<string, (event: MessageEvent) => void>(); close = vi.fn();
  constructor(public url: string, public options?: EventSourceInit) { Stream.instances.push(this); }
  addEventListener(type: string, listener: (event: MessageEvent) => void) { this.listeners.set(type, listener); }
  emit(type: string, value?: unknown) { this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify(value) })); }
}
const view = (accountId = 7) => <LocaleProvider><AnalystChat source={{ kind: "task", id: "t1" }} accountId={accountId} style="coach" subjectId="s1" comparisonId={null} disabled={false} evidence={[]} onEvidence={() => {}}/></LocaleProvider>;
beforeEach(() => { sessionStorage.clear(); localStorage.setItem("dashanbing-locale", "en"); Stream.instances = []; vi.stubGlobal("EventSource", Stream); });

test("sends scoped chat, replaces streamed message snapshots, and recovers history after refresh", async () => {
  let finished = false;
  const fetcher = vi.fn(async (input: string, init?: RequestInit) => {
    if (input.endsWith("/conversations")) return json({ id: "c1", messages: [] });
    if (input.endsWith("/messages") && init?.method === "POST") return json({ message_id: "u1", job_id: "j1" });
    return json({ id: "c1", messages: [{ id: "u1", role: "user", content: "What next?", citations: [], status: "completed" }, { id: "a1", role: "assistant", content: finished ? "Practice balance" : "", citations: [], status: finished ? "completed" : "running" }] });
  });
  vi.stubGlobal("fetch", fetcher);
  const user = userEvent.setup(); const rendered = render(view());
  await user.type(screen.getByRole("textbox", { name: "Ask the analyst" }), "What next?");
  await user.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(Stream.instances.length).toBe(1));
  expect(fetcher).toHaveBeenCalledWith("/api/v1/analyst/conversations", expect.objectContaining({ credentials: "include", body: JSON.stringify({ task_id: "t1", subject_id: "s1", locale: "en", style: "coach" }) }));
  expect(Stream.instances[0].options).toEqual({ withCredentials: true });
  act(() => {
    Stream.instances[0].emit("message", { id: "a1", role: "assistant", content: "Practice", citations: [], status: "running" });
    Stream.instances[0].emit("message", { id: "a1", role: "assistant", content: "Practice balance", citations: [], status: "completed" });
  });
  expect(screen.getAllByText("Practice balance")).toHaveLength(1);
  finished = true;
  rendered.unmount();
  expect(Stream.instances[0].close).toHaveBeenCalled();
  render(view());
  expect(await screen.findByText("Practice balance")).toBeVisible();
  expect(fetcher.mock.calls.filter(([input]) => input.endsWith("/conversations"))).toHaveLength(1);
});

test("an account switch cannot restore another account's stored conversation", async () => {
  sessionStorage.setItem("analyst:7:task:t1:s1::en:coach", "private-c1");
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  render(view(8));
  expect(screen.getByRole("textbox", { name: "Ask the analyst" })).toBeEnabled();
  expect(fetcher).not.toHaveBeenCalled();
});

test("an SSE disconnect recovers the complete message using authenticated GET", async () => {
  sessionStorage.setItem("analyst:7:task:t1:s1::en:coach", "c1");
  let reads = 0;
  vi.stubGlobal("fetch", vi.fn(async () => json({ id: "c1", messages: [{ id: "a1", role: "assistant", content: ++reads === 1 ? "" : "Recovered answer", citations: [], status: reads === 1 ? "running" : "completed" }] })));
  render(view());
  await waitFor(() => expect(Stream.instances).toHaveLength(1));
  act(() => Stream.instances[0].emit("error"));
  expect(await screen.findByText("Recovered answer")).toBeVisible();
  expect(screen.getByRole("textbox", { name: "Ask the analyst" })).toBeEnabled();
});


test("quick questions fill the composer, honor disabled states and enforce the backend 4000-character limit", async () => {
  vi.stubGlobal("fetch", vi.fn());
  const user = userEvent.setup(); const rendered = render(view());
  await user.click(screen.getByRole("button", { name: "Which plays should I rewatch?" }));
  expect(screen.getByRole("textbox", { name: "Ask the analyst" })).toHaveValue("Which plays should I rewatch?");
  expect(screen.getByRole("textbox", { name: "Ask the analyst" })).toHaveAttribute("maxlength", "4000");
  expect(fetch).not.toHaveBeenCalled();
  rendered.rerender(<LocaleProvider><AnalystChat source={{ kind: "task", id: "t1" }} accountId={7} style="coach" subjectId="s1" comparisonId={null} disabled={true} evidence={[]} onEvidence={() => {}}/></LocaleProvider>);
  for (const question of ["Which plays should I rewatch?", "What should I practice next?", "How does this compare?", "Roast my game"]) expect(screen.getByRole("button", { name: question })).toBeDisabled();
});

test("streamed messages only scroll the chat container when its reader is near the bottom", async () => {
  sessionStorage.setItem("analyst:7:task:t1:s1::en:coach", "c1");
  vi.stubGlobal("fetch", vi.fn(async () => json({ id: "c1", messages: [{ id: "a1", role: "assistant", content: "Initial reply", citations: [], status: "running" }] })));
  const pageScroll = vi.fn(); Element.prototype.scrollIntoView = pageScroll;
  render(view());
  await waitFor(() => expect(Stream.instances).toHaveLength(1));
  const log = screen.getByRole("log");
  Object.defineProperty(log, "scrollHeight", { value: 1000, configurable: true });
  Object.defineProperty(log, "clientHeight", { value: 200, configurable: true });
  log.scrollTop = 50; fireEvent.scroll(log);
  act(() => Stream.instances[0].emit("message", { id: "a1", role: "assistant", content: "Longer reply", citations: [], status: "running" }));
  expect(log.scrollTop).toBe(50);
  expect(pageScroll).not.toHaveBeenCalled();
  log.scrollTop = 800; fireEvent.scroll(log);
  Object.defineProperty(log, "scrollHeight", { value: 1200, configurable: true });
  act(() => Stream.instances[0].emit("message", { id: "a1", role: "assistant", content: "Longer finished reply", citations: [], status: "completed" }));
  expect(log.scrollTop).toBeGreaterThanOrEqual(1000);
  expect(pageScroll).not.toHaveBeenCalled();
});

test("retrying a failed send uses the existing conversation and the same request id", async () => {
  let attempts = 0;
  const ids: string[] = [];
  const fetcher = vi.fn(async (input: string, init?: RequestInit) => {
    if (input.endsWith("/conversations")) return json({ id: "c1", messages: [] });
    if (input.endsWith("/messages")) { ids.push(JSON.parse(String(init?.body)).request_id); if (++attempts === 1) throw new Error("Response lost"); return json({ message_id: "u1", job_id: "j1" }); }
    return json({ id: "c1", messages: [{ id: "u1", role: "user", content: "Retry me", citations: [], status: "completed" }] });
  });
  vi.stubGlobal("fetch", fetcher);
  const user = userEvent.setup(); render(view());
  await user.type(screen.getByRole("textbox", { name: "Ask the analyst" }), "Retry me");
  await user.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByRole("alert");
  await user.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Retry me");
  expect(ids).toHaveLength(2); expect(ids[0]).toBe(ids[1]);
  expect(fetcher.mock.calls.filter(([input]) => input.endsWith("/conversations"))).toHaveLength(1);
});
