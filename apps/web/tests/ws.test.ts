import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RealtimeClient } from "@/lib/ws";

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
    this.dispatch("close");
  }

  simulateOpen(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.dispatch("open");
  }

  simulateClose(): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.dispatch("close");
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
    expect(client.getStatus()).toBe("open");
  });

  it("never puts the token in the connection URL", () => {
    const client = newClient({ url: "wss://example.test/ws?channel=radar" });
    client.connect();
    expect(instanceAt(0).url).not.toContain("tok123");
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
