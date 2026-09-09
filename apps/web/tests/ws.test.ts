import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { logger } from "@/lib/logger";
import { deriveConnectionHealth, RECONNECT_GRACE_MS } from "@/lib/realtime-health";
import { KEEPALIVE_MS, RealtimeClient } from "@/lib/ws";

// T3.44e: same pattern as `tests/auto-refresh.test.tsx`'s `setVisibility` --
// a configurable getter on the real jsdom `document`, restored to "visible"
// by every keepalive test's own `beforeEach` below.
function setVisibility(state: DocumentVisibilityState): void {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

type Listener = (event?: unknown) => void;

/** Minimal fake of the browser WebSocket, controllable from the test. */
class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readonly CONNECTING = FakeWebSocket.CONNECTING;
  readonly OPEN = FakeWebSocket.OPEN;
  readonly CLOSING = FakeWebSocket.CLOSING;
  readonly CLOSED = FakeWebSocket.CLOSED;

  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  private listeners: Record<string, Listener[]> = {};

  constructor(public readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type: string, cb: Listener): void {
    (this.listeners[type] ??= []).push(cb);
  }

  removeEventListener(): void {}

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
    // A real browser `close()` with no arguments sends a Close frame with no
    // status code at all -- both ends observe that as code 1005 ("no status
    // code was present", RFC 6455 §7.1.5), `wasClean: true` (it is still a
    // proper closing handshake, just codeless). `RealtimeClient.close()`
    // itself never passes a code, so this default matches what its own
    // `handleClose` actually receives in production.
    this.dispatch("close", { code: 1005, reason: "", wasClean: true });
  }

  simulateOpen(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.dispatch("open");
  }

  /** Defaults mirror an unremarkable server-clean close; pass `{code, reason, wasClean}` to simulate a specific one (e.g. a 4401/4408/4403, or the VPS's real-world `{code: 1005, reason: "client disconnected"}`). */
  simulateClose(info: { code?: number; reason?: string; wasClean?: boolean } = {}): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.dispatch("close", { code: info.code ?? 1000, reason: info.reason ?? "", wasClean: info.wasClean ?? true });
  }

  simulateMessage(data: unknown): void {
    this.dispatch("message", { data: JSON.stringify(data) });
  }

  private dispatch(type: string, event?: unknown): void {
    for (const cb of this.listeners[type] ?? []) cb(event);
  }
}

function newClient(overrides: Partial<ConstructorParameters<typeof RealtimeClient>[0]> = {}) {
  return new RealtimeClient({
    url: "wss://example.test/ws",
    getAuthToken: () => "tok123",
    WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    ...overrides,
  });
}

/** `noUncheckedIndexedAccess`-safe accessor: fails the test loudly instead of asserting non-null. */
function instanceAt(index: number): FakeWebSocket {
  const socket = FakeWebSocket.instances[index];
  if (!socket) throw new Error(`expected a FakeWebSocket instance at index ${index}`);
  return socket;
}

beforeEach(() => {
  FakeWebSocket.instances = [];
});

describe("auth handshake", () => {
  it("sends { type: 'auth', token } (token at the top level) as the first message on open", async () => {
    // Contract T06 implements server-side in the api WS gateway -- token is
    // NOT nested under `payload`.
    const client = newClient();
    client.connect();
    const socket = instanceAt(0);
    socket.simulateOpen();

    await vi.waitFor(() => expect(socket.sent).toHaveLength(1));
    const [firstMessage] = socket.sent;
    if (!firstMessage) throw new Error("expected a sent message");
    expect(JSON.parse(firstMessage)).toEqual({ type: "auth", token: "tok123" });
  });

  it("never puts the token in the connection URL", () => {
    const client = newClient({ url: "wss://example.test/ws?channel=radar" });
    client.connect();
    expect(instanceAt(0).url).not.toContain("tok123");
  });

  // T3.44: the topbar's live-feed indicator (`liveFeedDown = status !== "open"`)
  // is only honest if "open" means the server actually accepted the
  // connection -- sending the auth frame and having it accepted are two
  // different facts, and a bad/expired token is rejected (4401) right after
  // the frame is sent.
  it("stays out of 'open' after sending the auth frame, until the server answers {type: 'authenticated'}", async () => {
    const client = newClient();
    client.connect();
    const socket = instanceAt(0);
    socket.simulateOpen();

    await vi.waitFor(() => expect(socket.sent).toHaveLength(1));
    expect(client.getStatus()).not.toBe("open");

    socket.simulateMessage({ type: "authenticated" });
    expect(client.getStatus()).toBe("open");
  });

  it("never sends a null/missing token, closes and logs instead so a silent server-side 4401 has a visible cause", async () => {
    const warn = vi.spyOn(logger, "warn").mockImplementation(() => undefined);
    const client = newClient({ getAuthToken: () => null });
    client.connect();
    const socket = instanceAt(0);
    socket.simulateOpen();

    await vi.waitFor(() => expect(socket.readyState).toBe(FakeWebSocket.CLOSED));
    expect(socket.sent).toHaveLength(0);
    expect(warn).toHaveBeenCalledWith("realtime_auth_token_missing", {});
    warn.mockRestore();
  });
});

describe("server heartbeat (T3.44d)", () => {
  it("answers { type: 'ping' } with { type: 'pong' } and never forwards it to onMessage", async () => {
    const onMessage = vi.fn();
    const client = newClient({ onMessage });
    client.connect();
    const socket = instanceAt(0);
    socket.simulateOpen();
    await vi.waitFor(() => expect(socket.sent).toHaveLength(1)); // the auth frame
    socket.simulateMessage({ type: "authenticated" });

    socket.simulateMessage({ type: "ping" });

    expect(socket.sent).toHaveLength(2);
    const [, pongFrame] = socket.sent;
    if (!pongFrame) throw new Error("expected a second sent message (the pong reply)");
    expect(JSON.parse(pongFrame)).toEqual({ type: "pong" });
    expect(onMessage).not.toHaveBeenCalledWith(expect.objectContaining({ type: "ping" }));
  });
});

describe("close diagnostics (T3.44d)", () => {
  it("records the native close event (code/reason/wasClean) even for this client's own close()", async () => {
    const client = newClient();
    client.connect();
    const socket = instanceAt(0);
    socket.simulateOpen();
    client.close();

    const diagnostics = client.getDiagnostics();
    expect(diagnostics.lastClose).toEqual({ code: 1005, reason: "", wasClean: true, at: expect.any(Number) });
  });

  it("records a server-sent close code/reason (e.g. 4408 pong timeout) the same way", async () => {
    const client = newClient();
    client.connect();
    const socket = instanceAt(0);
    socket.simulateOpen();
    socket.simulateClose({ code: 4408, reason: "pong timeout", wasClean: true });

    expect(client.getDiagnostics().lastClose).toEqual({ code: 4408, reason: "pong timeout", wasClean: true, at: expect.any(Number) });
  });

  // T3.44f (review of T3.44d, CRITICAL): `since` used to be stamped on
  // EVERY transition including "connecting", so it was already a real
  // timestamp before the first "open" ever happened -- this is exactly the
  // bug this task fixes; see the "grace window survives ..." describe block
  // below for the full multi-attempt proof.
  it("stays `null` through every connecting/closed attempt before the first ever `open`, then anchors once open", async () => {
    const client = newClient();
    expect(client.getDiagnostics().since).toBeNull();

    client.connect();
    expect(client.getDiagnostics().since).toBeNull(); // "connecting", never opened yet -- no anchor

    const socket = instanceAt(0);
    socket.simulateOpen();
    socket.simulateMessage({ type: "authenticated" });
    expect(client.getStatus()).toBe("open");
    const openSince = client.getDiagnostics().since;
    if (openSince === null) throw new Error("expected a `since` timestamp once open");
    expect(openSince).toBeGreaterThanOrEqual(0);
  });

  it("logs a client-requested close at debug, never warn -- it is expected, not an incident", async () => {
    const warn = vi.spyOn(logger, "warn").mockImplementation(() => undefined);
    const client = newClient();
    client.connect();
    instanceAt(0).simulateOpen();
    client.close();

    expect(warn).not.toHaveBeenCalledWith("realtime_closed_unexpectedly", expect.anything());
    warn.mockRestore();
  });

  it("logs an unexpected close (server-initiated or the browser dropping the socket) at warn, with code/reason/attempt", async () => {
    const warn = vi.spyOn(logger, "warn").mockImplementation(() => undefined);
    const client = newClient();
    client.connect();
    instanceAt(0).simulateOpen();
    instanceAt(0).simulateClose({ code: 1005, reason: "client disconnected", wasClean: true });

    expect(warn).toHaveBeenCalledWith("realtime_closed_unexpectedly", {
      code: 1005,
      reason: "client disconnected",
      wasClean: true,
      attempt: 0,
    });
    warn.mockRestore();
  });
});

describe("grace window survives a real reconnect loop (T3.44f, review of T3.44d)", () => {
  /** Same shape `live-status.tsx` builds from `useMarketChannels`'s diagnostics -- reads straight off the client under test, at whatever fake-timer instant the test is currently at. */
  function healthOf(client: RealtimeClient) {
    return deriveConnectionHealth({
      status: client.getStatus(),
      since: client.getDiagnostics().since,
      now: Date.now(),
      lastClose: client.getDiagnostics().lastClose,
    });
  }

  it("never reads live before the very first `open` -- no initial-load grace window", () => {
    const client = newClient();
    client.connect(); // still "connecting", has never once been "open"
    expect(client.getStatus()).toBe("connecting");
    const health = healthOf(client);
    expect(health.live).toBe(false);
    expect(health.since).toBeNull();
  });

  it("stays not-live through a minutes-long outage across many backoff attempts, never flashing 'ao vivo' at any retry", async () => {
    vi.useFakeTimers();
    try {
      // random: () => 1 => the exponential delay's full value, no jitter
      // discount (same convention as "reconnect backoff schedule" below) --
      // deterministic timing is what lets this test advance by exact
      // amounts and know precisely which transition it just crossed.
      const client = newClient({ baseBackoffMs: 500, maxBackoffMs: 15_000, random: () => 1 });
      client.connect();
      instanceAt(0).simulateOpen();
      instanceAt(0).simulateMessage({ type: "authenticated" });
      expect(client.getStatus()).toBe("open");
      expect(healthOf(client).live).toBe(true);

      // The outage begins -- the server, or the browser tearing the socket
      // down under it (T3.44d's VPS evidence), closes the connection.
      instanceAt(0).simulateClose({ code: 1005, reason: "client disconnected", wasClean: true });
      expect(healthOf(client).live).toBe(true); // still inside RECONNECT_GRACE_MS
      const outageAnchor = client.getDiagnostics().since;
      if (outageAnchor === null) throw new Error("expected an outage anchor once the client has been open before");

      await vi.advanceTimersByTimeAsync(RECONNECT_GRACE_MS);
      expect(healthOf(client).live).toBe(false); // grace exhausted, outage still ongoing

      // Drive ~10 more real backoff attempts (each one a fresh "connecting"
      // via `open()`, closed again before the next attempt) -- a couple of
      // minutes of continuous outage that never actually recovers. BEFORE
      // this fix, every single "connecting" transition re-stamped `since`
      // to "now", handing `deriveConnectionHealth` a brand new grace window
      // and flashing `live: true` for an instant on every retry; this loop
      // is the reproduction of exactly that CRITICAL finding.
      for (let i = 0; i < 10; i += 1) {
        await vi.advanceTimersByTimeAsync(15_000); // >= the capped max backoff, always enough to reach the next attempt
        expect(client.getStatus()).toBe("connecting");
        // The critical assertion: not live even the instant a fresh
        // "connecting" transition just fired.
        expect(healthOf(client).live).toBe(false);
        // The anchor itself never moved across any of these attempts --
        // the actual mechanism of the fix, not just its observable effect.
        expect(client.getDiagnostics().since).toBe(outageAnchor);
        instanceAt(FakeWebSocket.instances.length - 1).simulateClose({ code: 1005, reason: "client disconnected", wasClean: true });
        expect(healthOf(client).live).toBe(false);
      }
      // ~10 * 15s of backoff loop alone is 2.5 minutes -- a genuinely
      // minutes-long outage, read as "not live" throughout, never once.
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("visible-tab keepalive (T3.44e)", () => {
  // The server's 15-minute idle timeout (`session.py`'s `IDLE_TIMEOUT_SECONDS`,
  // close code 4409, this brief's VPS evidence) only resets on a
  // CLIENT-initiated frame -- this class's own `{"type":"ping"}` sent on a
  // schedule while the tab is visible. `random: () => 0.5` pins the ±10s
  // jitter to exactly 0 (`(0.5*2-1)*JITTER === 0`), so `KEEPALIVE_MS` is the
  // exact, deterministic delay in every test below.

  async function connectAndAuthenticate(client: RealtimeClient): Promise<FakeWebSocket> {
    client.connect();
    const socket = instanceAt(FakeWebSocket.instances.length - 1);
    socket.simulateOpen();
    await vi.advanceTimersByTimeAsync(0); // flushes the `await getAuthToken()` microtask
    socket.simulateMessage({ type: "authenticated" });
    return socket;
  }

  beforeEach(() => {
    vi.useFakeTimers();
    setVisibility("visible");
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("sends {type:'ping'} once KEEPALIVE_MS elapses on a visible, open, authenticated tab", async () => {
    const client = newClient({ random: () => 0.5 });
    const socket = await connectAndAuthenticate(client);
    const sentAfterAuth = socket.sent.length; // just the auth frame

    await vi.advanceTimersByTimeAsync(KEEPALIVE_MS - 1);
    expect(socket.sent).toHaveLength(sentAfterAuth);

    await vi.advanceTimersByTimeAsync(1);
    expect(socket.sent).toHaveLength(sentAfterAuth + 1);
    const lastFrame = socket.sent[socket.sent.length - 1];
    if (!lastFrame) throw new Error("expected a keepalive ping frame");
    expect(JSON.parse(lastFrame)).toEqual({ type: "ping" });
  });

  it("keeps sending on every KEEPALIVE_MS tick, not just once", async () => {
    const client = newClient({ random: () => 0.5 });
    const socket = await connectAndAuthenticate(client);
    const sentAfterAuth = socket.sent.length;

    await vi.advanceTimersByTimeAsync(KEEPALIVE_MS);
    await vi.advanceTimersByTimeAsync(KEEPALIVE_MS);
    expect(socket.sent).toHaveLength(sentAfterAuth + 2);
  });

  it("sends nothing while the tab is hidden, even across several KEEPALIVE_MS intervals", async () => {
    setVisibility("hidden");
    const client = newClient({ random: () => 0.5 });
    const socket = await connectAndAuthenticate(client);
    const sentAfterAuth = socket.sent.length;

    await vi.advanceTimersByTimeAsync(KEEPALIVE_MS * 3);
    expect(socket.sent).toHaveLength(sentAfterAuth);
  });

  it("sends one immediate ping on visibilitychange back to visible when the last activity is already >= KEEPALIVE_MS old", async () => {
    const client = newClient({ random: () => 0.5 });
    const socket = await connectAndAuthenticate(client);

    setVisibility("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(KEEPALIVE_MS * 2); // hidden the whole time -- nothing scheduled
    const sentWhileHidden = socket.sent.length;

    setVisibility("visible");
    document.dispatchEvent(new Event("visibilitychange"));

    expect(socket.sent).toHaveLength(sentWhileHidden + 1);
    const lastFrame = socket.sent[socket.sent.length - 1];
    if (!lastFrame) throw new Error("expected the immediate keepalive ping frame");
    expect(JSON.parse(lastFrame)).toEqual({ type: "ping" });
  });

  it("does NOT send an immediate ping on visibilitychange if the last activity is still recent", async () => {
    const client = newClient({ random: () => 0.5 });
    const socket = await connectAndAuthenticate(client);
    const sentAfterAuth = socket.sent.length;

    setVisibility("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(1_000); // well under KEEPALIVE_MS

    setVisibility("visible");
    document.dispatchEvent(new Event("visibilitychange"));

    expect(socket.sent).toHaveLength(sentAfterAuth); // no redundant frame
  });

  it("clears the keepalive timer on close() -- no ping fires after the socket is gone", async () => {
    const client = newClient({ random: () => 0.5 });
    const socket = await connectAndAuthenticate(client);

    client.close();
    const sentAtClose = socket.sent.length;
    await vi.advanceTimersByTimeAsync(KEEPALIVE_MS * 2);
    expect(socket.sent).toHaveLength(sentAtClose);
  });

  it("clears the keepalive timer on an unexpected server close too", async () => {
    const client = newClient({ random: () => 0.5 });
    const socket = await connectAndAuthenticate(client);

    socket.simulateClose({ code: 4409, reason: "idle timeout", wasClean: true });
    const sentAtClose = socket.sent.length;
    // The client's own reconnect backoff may open a brand new socket in the
    // background (irrelevant here) -- what matters is that THIS now-closed
    // socket never receives another keepalive ping.
    await vi.advanceTimersByTimeAsync(KEEPALIVE_MS * 2);
    expect(socket.sent).toHaveLength(sentAtClose);
  });

  it("ignores the server's {type:'pong'} reply to its own keepalive ping -- no reply-to-a-reply, no double handling with the server-ping/client-pong pair", async () => {
    const onMessage = vi.fn();
    const client = newClient({ random: () => 0.5, onMessage });
    const socket = await connectAndAuthenticate(client);

    await vi.advanceTimersByTimeAsync(KEEPALIVE_MS); // this client's own ping fires
    const sentAfterOwnPing = socket.sent.length;

    socket.simulateMessage({ type: "pong" });

    expect(socket.sent).toHaveLength(sentAfterOwnPing); // no frame sent in response to a pong
  });

  it("never mistakes its OWN reply to the server's heartbeat ping ({type:'pong'}) for client activity that would skip an owed keepalive", async () => {
    // The server's `session.mark_frame()` deliberately does not reset on a
    // client's pong reply to the SERVER's own ping (module doc, `lib/ws.ts`)
    // -- this client's `lastActivityAt` must agree, or a visibility flip
    // could wrongly skip a ping the server still needs.
    const client = newClient({ random: () => 0.5 });
    const socket = await connectAndAuthenticate(client);

    setVisibility("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(KEEPALIVE_MS); // hidden -- server's heartbeat still arrives
    socket.simulateMessage({ type: "ping" }); // server heartbeat -> this class replies {type:"pong"} via send()
    const sentAfterServerPingReply = socket.sent.length;

    setVisibility("visible");
    document.dispatchEvent(new Event("visibilitychange"));

    // Despite the pong reply just above, KEEPALIVE_MS has already elapsed
    // since authentication -- the immediate keepalive ping must still fire.
    expect(socket.sent).toHaveLength(sentAfterServerPingReply + 1);
    const lastFrame = socket.sent[socket.sent.length - 1];
    if (!lastFrame) throw new Error("expected the immediate keepalive ping frame");
    expect(JSON.parse(lastFrame)).toEqual({ type: "ping" });
  });
});

describe("reconnect backoff schedule", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("doubles the delay each attempt, starting at baseBackoffMs (random pinned to 1 => no jitter discount)", async () => {
    const client = newClient({ baseBackoffMs: 100, maxBackoffMs: 10_000, random: () => 1 });
    client.connect();
    expect(FakeWebSocket.instances).toHaveLength(1);

    instanceAt(0).simulateClose();
    await vi.advanceTimersByTimeAsync(99);
    expect(FakeWebSocket.instances).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances).toHaveLength(2); // 100ms

    instanceAt(1).simulateClose();
    await vi.advanceTimersByTimeAsync(199);
    expect(FakeWebSocket.instances).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances).toHaveLength(3); // 200ms

    instanceAt(2).simulateClose();
    await vi.advanceTimersByTimeAsync(400);
    expect(FakeWebSocket.instances).toHaveLength(4); // 400ms
  });

  it("caps the exponential delay at maxBackoffMs before jitter is applied", async () => {
    const client = newClient({ baseBackoffMs: 100, maxBackoffMs: 250, random: () => 1 });
    client.connect();

    instanceAt(0).simulateClose(); // attempt 0 -> 100ms
    await vi.advanceTimersByTimeAsync(100);
    instanceAt(1).simulateClose(); // attempt 1 -> 200ms
    await vi.advanceTimersByTimeAsync(200);
    instanceAt(2).simulateClose(); // attempt 2 -> would be 400ms, capped to 250ms
    await vi.advanceTimersByTimeAsync(250);

    expect(FakeWebSocket.instances).toHaveLength(4);
  });

  it("does not reconnect after an explicit close()", async () => {
    const client = newClient({ baseBackoffMs: 50 });
    client.connect();
    client.close();

    await vi.advanceTimersByTimeAsync(5000);
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(client.getStatus()).toBe("closed");
  });

  it("applies bounded jitter: delay stays within [0.5x, 1.0x] of the exponential value", async () => {
    // random() => 0 is the low end of the jitter range (0.5 * exponential);
    // random() => 1 is the high end (1.0 * exponential, verified above).
    const client = newClient({ baseBackoffMs: 100, maxBackoffMs: 10_000, random: () => 0 });
    client.connect();

    instanceAt(0).simulateClose(); // attempt 0 -> exponential 100ms, jittered to 50ms
    await vi.advanceTimersByTimeAsync(49);
    expect(FakeWebSocket.instances).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("gives two clients with different random sources different reconnect delays", async () => {
    const lowJitterClient = newClient({ baseBackoffMs: 1000, maxBackoffMs: 10_000, random: () => 0 });
    const highJitterClient = newClient({ baseBackoffMs: 1000, maxBackoffMs: 10_000, random: () => 1 });

    lowJitterClient.connect();
    highJitterClient.connect();
    expect(FakeWebSocket.instances).toHaveLength(2);

    instanceAt(0).simulateClose(); // low: exponential 1000ms * 0.5 = 500ms
    instanceAt(1).simulateClose(); // high: exponential 1000ms * 1.0 = 1000ms

    await vi.advanceTimersByTimeAsync(500);
    // Only the low-jitter client has reconnected at the 500ms mark.
    expect(FakeWebSocket.instances).toHaveLength(3);

    await vi.advanceTimersByTimeAsync(500);
    // The high-jitter client reconnects only once its full 1000ms elapses.
    expect(FakeWebSocket.instances).toHaveLength(4);
  });
});
