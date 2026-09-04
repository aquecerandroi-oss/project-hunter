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
    // Wire shape is `{ type: "auth", token }` -- token at the top level, not
    // `RealtimeMessage`'s usual `payload` envelope. See the class doc.
    if (this.ws && this.ws.readyState === this.ws.OPEN) {
      this.ws.send(JSON.stringify({ type: "auth", token }));
    }
    this.setStatus("open");
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const message = JSON.parse(String(event.data)) as RealtimeMessage;
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
