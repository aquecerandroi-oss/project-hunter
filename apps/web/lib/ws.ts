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

export interface RealtimeMessage<T = unknown> {
  type: string;
  payload: T;
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
  private attempt = 0;
  private closedByUser = true;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

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
    }
  }

  getStatus(): RealtimeStatus {
    return this.status;
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
    socket.addEventListener("close", () => {
      this.handleClose();
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

  private handleClose(): void {
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

  private setStatus(status: RealtimeStatus): void {
    this.status = status;
    this.options.onStatusChange?.(status);
  }
}
