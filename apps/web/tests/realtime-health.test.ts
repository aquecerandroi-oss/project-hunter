import { describe, expect, it } from "vitest";

import { deriveConnectionHealth, RECONNECT_GRACE_MS } from "@/lib/realtime-health";
import type { RealtimeCloseInfo } from "@/lib/ws";

const CLOSE: RealtimeCloseInfo = { code: 1005, reason: "client disconnected", wasClean: true, at: 0 };

describe("deriveConnectionHealth (T3.44d)", () => {
  it("is live whenever status is 'open', regardless of any past close", () => {
    const health = deriveConnectionHealth({ status: "open", since: 1_000, now: 1_000, lastClose: CLOSE });
    expect(health.live).toBe(true);
    expect(health.since).toBe(1_000);
  });

  it("stays live through a disconnection shorter than the grace window -- the client's own backoff is trusted to land", () => {
    const since = 10_000;
    const health = deriveConnectionHealth({ status: "closed", since, now: since + RECONNECT_GRACE_MS - 1, lastClose: CLOSE });
    expect(health.live).toBe(true);
  });

  it("flips to not-live once the CURRENT disconnection outlasts the grace window", () => {
    const since = 10_000;
    const health = deriveConnectionHealth({ status: "closed", since, now: since + RECONNECT_GRACE_MS, lastClose: CLOSE });
    expect(health.live).toBe(false);
  });

  it("treats a never-yet-connected client (since=null) as immediately not-live, never a false 'ao vivo'", () => {
    const health = deriveConnectionHealth({ status: "connecting", since: null, now: 5_000, lastClose: null });
    expect(health.live).toBe(false);
    expect(health.since).toBeNull();
  });

  it("formats the last close as '<reason> (<code>)' for the tooltip", () => {
    const health = deriveConnectionHealth({ status: "closed", since: 0, now: 100_000, lastClose: CLOSE });
    expect(health.lastCloseLabel).toBe("client disconnected (1005)");
  });

  it("falls back to a plain label when the server/browser sent no reason string", () => {
    const health = deriveConnectionHealth({
      status: "closed",
      since: 0,
      now: 100_000,
      lastClose: { code: 1005, reason: "", wasClean: true, at: 0 },
    });
    expect(health.lastCloseLabel).toBe("sem motivo informado (1005)");
  });

  it("is null before this client has ever closed a socket", () => {
    const health = deriveConnectionHealth({ status: "connecting", since: 0, now: 0, lastClose: null });
    expect(health.lastCloseLabel).toBeNull();
  });

  it("honours a caller-supplied graceMs instead of the default", () => {
    const since = 0;
    const health = deriveConnectionHealth({ status: "closed", since, now: 2_000, lastClose: null, graceMs: 1_000 });
    expect(health.live).toBe(false);
  });
});

describe("deriveConnectionHealth: the server's 15-minute idle close (4409) (T3.44e)", () => {
  const IDLE_CLOSE: RealtimeCloseInfo = { code: 4409, reason: "idle timeout", wasClean: true, at: 0 };

  it("names the reason in plain Portuguese instead of echoing the server's raw English string", () => {
    const health = deriveConnectionHealth({ status: "closed", since: 0, now: 100_000, lastClose: IDLE_CLOSE });
    expect(health.lastCloseLabel).toBe("encerrado por ociosidade (15 min)");
  });

  it("a 4409 close followed by a successful reconnect inside the grace window still reads 'ao vivo'", () => {
    // `status: "open"` is unconditional in `deriveConnectionHealth` -- the
    // PAST close code never blocks a live reading once the client is
    // actually reconnected, grace window or not.
    const health = deriveConnectionHealth({ status: "open", since: 50_000, now: 50_100, lastClose: IDLE_CLOSE });
    expect(health.live).toBe(true);
    // ... and the tooltip still remembers the idle close by name, for a
    // viewer wondering why the feed blipped at all.
    expect(health.lastCloseLabel).toBe("encerrado por ociosidade (15 min)");
  });

  it("a 4409 close still inside the grace window (reconnect not yet confirmed) also reads 'ao vivo'", () => {
    const since = 10_000;
    const health = deriveConnectionHealth({ status: "closed", since, now: since + RECONNECT_GRACE_MS - 1, lastClose: IDLE_CLOSE });
    expect(health.live).toBe(true);
  });
});
