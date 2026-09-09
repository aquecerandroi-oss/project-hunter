import { logger } from "@/lib/logger";

/**
 * Typed realtime client for docs/ARCHITECTURE.md §5.2 (Redis pub/sub ->
 * `api` -> browser WebSocket). Implemented in full but NOT wired up
 * anywhere in M0 -- there is no `market-worker`/`scanner-worker` publishing
 * on `rt:*` channels yet, and the `api` WS gateway itself lands after this
 * task. `hooks/useRealtime.ts` is the only sanctioned way to use this from
 * components, and it defaults `enabled` to `false` until M1.
 *
 * Per docs/SECURITY.md §1: the auth token is sent as the FIRST message on
 * the socket, never in the query string; the server closes the connection
 * if it doesn't authenticate within 5s.
 *
 * Wire shape `{ type: "auth", token }` (token at the top level, NOT nested
 * under `payload`) is the contract T06 implements server-side in the `api`
 * WS gateway -- keep this in sync with that handler.
 */

export type RealtimeStatus = "idle" | "connecting" | "open" | "closed" | "error";

/**
 * T3.44e: the server closes an AUTHENTICATED-but-idle socket after 15 min
 * (`session.py`'s `IDLE_TIMEOUT_SECONDS`, close code 4409). A server `ping`/
 * client `pong` does NOT reset that clock (`endpoint.py`: "deliberately not
 * mark_frame() -- a pong is our own heartbeat"); only a CLIENT-initiated
 * frame does. The topbar's receive-only `rt:system` socket hit this every
 * ~15 min by design (VPS evidence: 10 `4409`/hour on a visible tab).
 * `KEEPALIVE_MS` is this client saying "someone is looking" while the
 * document is actually visible -- a hidden tab still times out on purpose.
 */
export const KEEPALIVE_MS = 5 * 60_000;
/** ± this, so many tabs on the same cadence don't all ping in the same instant (same jitter reasoning as `scheduleReconnect` below). */
export const KEEPALIVE_JITTER_MS = 10_000;

export interface RealtimeMessage<T = unknown> {
  type: string;
  payload: T;
}

/** The native `CloseEvent` this client last observed, kept after the socket itself is gone -- `live-status.tsx`'s tooltip (T3.44d) shows this as the reason a viewer's feed dropped, instead of a bare dot with no story. */
export interface RealtimeCloseInfo {
  code: number;
  reason: string;
  wasClean: boolean;
  /** `Date.now()` when this close was observed. */
  at: number;
}

/** Snapshot of what a consumer needs to render an honest status line: how long the CURRENT status has held, and the last close this client instance has seen (survives reconnects, cleared only by a brand new `RealtimeClient`). */
export interface RealtimeDiagnostics {
  /** `Date.now()` the current `status` began, or `null` before the first transition. */
  since: number | null;
  lastClose: RealtimeCloseInfo | null;
  /** Reconnect attempts since the last successful `open` (`scheduleReconnect`'s own counter). */
  attempt: number;
}

export interface RealtimeClientOptions {
  url: string;
  getAuthToken: () => Promise<string | null> | string | null;
  onMessage?: ((message: RealtimeMessage) => void) | undefined;
  onStatusChange?: ((status: RealtimeStatus) => void) | undefined;
  /** Base delay for exponential backoff, ms. Default 500. */
  baseBackoffMs?: number | undefined;
  /** Backoff ceiling, ms. Default 15000. */
  maxBackoffMs?: number | undefined;
  /**
   * RNG used for reconnect jitter, `() => number` in `[0, 1)`. Injectable so
   * tests can make delays deterministic; defaults to `Math.random`. Jitter
   * prevents many clients reconnecting in lockstep (thundering herd) after a
   * shared outage.
   */
  random?: (() => number) | undefined;
  /** Injectable for tests; defaults to the global `WebSocket`. */
  WebSocketImpl?: typeof WebSocket | undefined;
}

export class RealtimeClient {
  private ws: WebSocket | null = null;
  private status: RealtimeStatus = "idle";
  private statusSince: number | null = null;
  private everOpened = false; // T3.44f: has this instance EVER reached "open" -- see `setStatus`.
  private lastClose: RealtimeCloseInfo | null = null;
  private attempt = 0;
  private closedByUser = true;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  // T3.44e (additive, independent of the T3.44d fields above): visible-tab keepalive state.
  private keepaliveTimer: ReturnType<typeof setTimeout> | null = null;
  /** `Date.now()` of the last CLIENT-initiated frame sent (mirrors `session.mark_frame()`); used by `handleVisibilityChange` below. */
  private lastActivityAt: number | null = null;

  constructor(private readonly options: RealtimeClientOptions) {}

  connect(): void {
    this.closedByUser = false;
    this.attempt = 0;
    this.open();
  }

  close(): void {
    this.closedByUser = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.setStatus("closed");
  }

  send(message: RealtimeMessage): void {
    if (this.ws && this.ws.readyState === this.ws.OPEN) {
      this.ws.send(JSON.stringify(message));
      // T3.44e: mirrors `session.mark_frame()` -- a client `ping`/`subscribe`/
      // `unsubscribe` resets the server's idle clock, but this client's own
      // `pong` reply to the SERVER's heartbeat deliberately does not, so it
      // must not count as activity here either (else a visibility flip could
      // skip a keepalive ping the server still needs).
      if (message.type !== "pong") this.lastActivityAt = Date.now();
    }
  }

  getStatus(): RealtimeStatus {
    return this.status;
  }

  /** `since`/`lastClose`/`attempt` for a consumer's status line (T3.44d) -- a snapshot, not a subscription; callers read it from inside their own `onStatusChange`. */
  getDiagnostics(): RealtimeDiagnostics {
    return { since: this.statusSince, lastClose: this.lastClose, attempt: this.attempt };
  }

  private open(): void {
    const WebSocketCtor = this.options.WebSocketImpl ?? WebSocket;
    this.setStatus("connecting");
    const socket = new WebSocketCtor(this.options.url);
    this.ws = socket;
    socket.addEventListener("open", () => {
      this.attempt = 0;
      void this.authenticate();
    });
    socket.addEventListener("message", (event: MessageEvent) => {
      this.handleMessage(event);
    });
    socket.addEventListener("close", (event: CloseEvent) => {
      this.handleClose(event);
    });
    socket.addEventListener("error", () => {
      this.setStatus("error");
    });
  }

  private async authenticate(): Promise<void> {
    const token = await this.options.getAuthToken();
    if (!this.ws || this.ws.readyState !== this.ws.OPEN) return;
    // T3.44: a caller whose auth provider hasn't resolved a token yet (e.g.
    // Clerk's `getToken()` racing this socket's own `open` event) used to
    // still get `{"type":"auth","token":null}` sent -- the server's
    // `realtime/endpoint.py` `_authenticate` treats that exactly like a
    // missing token and closes with 4401 near-instantly, but nothing here
    // ever logged it, so the topbar just flapped between "open" and
    // "closed" with no visible reason. Closing proactively (and logging
    // why) turns that into one visible warning per attempt instead of a
    // silent, unexplained reconnect loop.
    if (!token) {
      logger.warn("realtime_auth_token_missing", {});
      this.ws.close();
      return;
    }
    // Wire shape is `{ type: "auth", token }` -- token at the top level, not
    // `RealtimeMessage`'s usual `payload` envelope. See the class doc.
    this.ws.send(JSON.stringify({ type: "auth", token }));
    // `status` becomes "open" only in `handleMessage`, once the server
    // actually answers `{"type":"authenticated"}` -- sending this frame is
    // not the same fact as the server having accepted it (an expired or
    // otherwise-rejected token closes the socket, 4401, right after this
    // point). Flipping to "open" here regardless -- the previous
    // behaviour -- told every `liveFeedDown` caller (the topbar included)
    // that the realtime channel was live for the fraction of a second
    // between sending this frame and the server's close, which is exactly
    // backwards: it hid the failure instead of reporting it.
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const message = JSON.parse(String(event.data)) as RealtimeMessage;
      // T3.44d: the server's 25s heartbeat (`realtime/endpoint.py`'s
      // `_heartbeat`) closes any socket that has not answered a `ping` by
      // the time the NEXT one is due (4408 "pong timeout") -- answered here,
      // once, for every caller of this client. `hooks/useRealtime.ts`
      // (Radar's `rt:radar` channel) forwarded every frame including this
      // one straight to its own `onMessage` and never replied, so that
      // socket was closed by the server on a ~25-50s clock regardless of
      // anything else in this file; `useMarketChannels.ts` had its own copy
      // of this same reply at the hook layer, now redundant and removed
      // there. Never forwarded to `onMessage` -- there is nothing for a
      // caller to do with it once this class has already answered.
      if (message.type === "ping") {
        this.send({ type: "pong" } as unknown as RealtimeMessage);
        return;
      }
      // The one frame this class itself acts on -- see `authenticate()`'s
      // doc. Still forwarded to `onMessage` below like any other frame
      // (`useMarketChannels`'s `handleFrame` already ignores unrecognized
      // `type`s harmlessly).
      if (message.type === "authenticated") this.setStatus("open");
      this.options.onMessage?.(message);
    } catch (error) {
      logger.warn("realtime_message_parse_failed", { error: String(error) });
    }
  }

  private handleClose(event: CloseEvent): void {
    // `event` carries what the browser actually observed on the wire --
    // `code`/`reason` empty (browser convention 1005, "no status code") for
    // this client's OWN `close()` with no arguments, or whatever the server
    // sent (4401/4403/4408/4409/4429, or the VPS's real-world 1005 "client
    // disconnected" when the *browser itself* tears the connection down on
    // a hard navigation/tab close -- T3.44d's evidence). Recorded even for a
    // close this client requested itself, because the tooltip
    // (`live-status.tsx`) shows the LAST close either way once the socket is
    // ever not "open".
    this.lastClose = { code: event.code, reason: event.reason, wasClean: event.wasClean, at: Date.now() };
    // `closedByUser` closes (component unmount, org switch) are routine and
    // logged at `debug` only; anything this client did not ask for --
    // server-initiated or the browser dropping the connection out from
    // under it -- is worth a `warn` with the same detail the VPS's
    // `ws_closed` line carries server-side (T3.44b), so a repeat of this
    // symptom has a client-side log to match it against.
    if (this.closedByUser) {
      logger.debug("realtime_closed", { code: event.code, reason: event.reason, wasClean: event.wasClean });
    } else {
      logger.warn("realtime_closed_unexpectedly", {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean,
        attempt: this.attempt,
      });
    }
    this.ws = null;
    this.setStatus("closed");
    if (this.closedByUser) return;
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    const base = this.options.baseBackoffMs ?? 500;
    const max = this.options.maxBackoffMs ?? 15000;
    const random = this.options.random ?? Math.random;
    const exponential = Math.min(max, base * 2 ** this.attempt);
    // Full jitter is [0, exponential]; we use "half jitter" ([0.5, 1.0] of
    // the exponential value) so the delay never collapses to ~0 and clients
    // still spread out instead of reconnecting in lockstep.
    const delay = exponential * (0.5 + random() * 0.5);
    this.attempt += 1;
    this.reconnectTimer = setTimeout(() => {
      if (!this.closedByUser) this.open();
    }, delay);
  }

  /**
   * T3.44f: anchor `statusSince` on the start of the CURRENT disconnection,
   * not the current sub-state -- stamping it on every "connecting" retry
   * reset the grace window each time, and did the same before the first
   * ever `open` (`!everOpened` keeps it `null` -- `Infinity` ms, never live).
   */
  private setStatus(status: RealtimeStatus): void {
    const wasOpen = this.status === "open";
    this.status = status;
    if (status === "open") {
      this.everOpened = true;
      this.statusSince = Date.now();
    } else if (wasOpen) {
      this.statusSince = Date.now(); // first step of a new outage
    }
    this.options.onStatusChange?.(status);
    // T3.44e (additive): keepalive only ever runs while "open"; any other
    // status must not leave a timer armed against a socket that is gone.
    if (status === "open") this.startKeepalive();
    else this.stopKeepalive();
  }

  // --- T3.44e: visible-tab keepalive (additive) ---------------------------
  // While visible and "open", sends a CLIENT `{"type":"ping"}` every
  // `KEEPALIVE_MS` (jittered) -- distinct from the SERVER's own `ping`
  // already answered in `handleMessage` above. The server's `{"type":
  // "pong"}` reply is not `"ping"`, so it already falls through
  // `handleMessage`'s existing branch untouched: no new handling needed,
  // no double-handling with T3.44d's server-ping/client-pong pair.

  private startKeepalive(): void {
    // The server's idle clock starts at authentication, not at this
    // instance's first sent frame -- mirrored here so a visibility flip
    // moments after connecting doesn't read "infinitely idle" and fire a
    // redundant immediate ping.
    this.lastActivityAt = Date.now();
    if (typeof document === "undefined") return; // SSR / non-browser test doubles never keepalive
    document.addEventListener("visibilitychange", this.handleVisibilityChange);
    this.scheduleKeepalive();
  }

  private stopKeepalive(): void {
    if (this.keepaliveTimer) {
      clearTimeout(this.keepaliveTimer);
      this.keepaliveTimer = null;
    }
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", this.handleVisibilityChange);
    }
  }

  /** Arms the next keepalive ping, or does nothing if the tab is currently hidden -- a hidden tab is meant to hit the server's idle timeout, not be kept alive from behind the scenes. */
  private scheduleKeepalive(): void {
    if (this.keepaliveTimer) {
      clearTimeout(this.keepaliveTimer);
      this.keepaliveTimer = null;
    }
    if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
    const random = this.options.random ?? Math.random;
    const jitter = (random() * 2 - 1) * KEEPALIVE_JITTER_MS; // uniform in [-JITTER, +JITTER]
    const delay = Math.max(0, KEEPALIVE_MS + jitter);
    this.keepaliveTimer = setTimeout(() => {
      this.send({ type: "ping", payload: undefined });
      this.scheduleKeepalive();
    }, delay);
  }

  /**
   * A class field (not a method) so add/removeEventListener above always
   * see the same reference. Hidden: cancels the pending timer -- a
   * background tab is not "someone looking" and must still time out.
   * Back to visible: sends one ping immediately if last activity is
   * already `>= KEEPALIVE_MS` old, then resumes the regular cadence.
   */
  private readonly handleVisibilityChange = (): void => {
    if (typeof document === "undefined") return;
    if (document.visibilityState !== "visible") {
      if (this.keepaliveTimer) {
        clearTimeout(this.keepaliveTimer);
        this.keepaliveTimer = null;
      }
      return;
    }
    if (this.status !== "open") return;
    const idleForMs = this.lastActivityAt === null ? Infinity : Date.now() - this.lastActivityAt;
    if (idleForMs >= KEEPALIVE_MS) this.send({ type: "ping", payload: undefined });
    this.scheduleKeepalive();
  };
}
