"use client";

import { useEffect, useRef, useState } from "react";

import { logger } from "@/lib/logger";
import { RealtimeClient, type RealtimeMessage, type RealtimeStatus } from "@/lib/ws";

/**
 * Multi-channel realtime subscriptions over ONE WebSocket connection, per
 * the actual gateway protocol (`apps/api/hunter_api/realtime/endpoint.py`):
 * auth as the first frame (handled by `RealtimeClient` itself), then
 * `{"type":"subscribe"|"unsubscribe","channels":[...]}`, incoming data as
 * `{"channel":..., "data":"<json>"}`, and a `{"type":"ping"}` that must be
 * answered with `{"type":"pong"}` or the server closes the socket (4408).
 *
 * `hooks/useRealtime.ts` intentionally isn't reused here: it opens one
 * connection per single channel baked into the URL, which cannot express
 * "up to MAX_CHANNELS_PER_CONNECTION (50) channels on one socket, diffed as
 * the caller's desired set changes" -- exactly what the markets list (one
 * channel per visible row), the market detail page (one channel) and the
 * live-status widget (`rt:system`) all need. This is the ONLY hook allowed
 * to import `@/lib/ws` directly (ESLint boundary: `components/**` cannot).
 */

const MAX_CHANNELS_PER_CONNECTION = 50;

export interface UseMarketChannelsOptions {
  /** Desired channel set, e.g. the symbols currently visible in a virtualized table. Capped at 50. */
  channels: string[];
  getAuthToken: () => Promise<string | null> | string | null;
  /** Defaults to `true` -- callers pass `false` while `NEXT_PUBLIC_WS_URL` or auth isn't ready yet. */
  enabled?: boolean;
  /**
   * Push-based alternative to reading `messages` back out of the hook's own
   * state: called synchronously from the socket's own message handler, so a
   * caller that needs to *accumulate* updates (e.g. merging one exchange's
   * status into a map of many) can call its own `setState` from here without
   * doing it inside a `useEffect` that merely watches `messages` change --
   * the rules-of-hooks lint flags that shape as a needless cascading render.
   */
  onMessage?: (channel: string, payload: unknown) => void;
}

export interface UseMarketChannelsResult {
  status: RealtimeStatus;
  /** Latest decoded payload per channel name, e.g. `messages["rt:market:binance:BTCUSDT"]`. */
  messages: Record<string, unknown>;
}

interface ChannelEnvelope {
  channel?: string;
  data?: string;
  type?: string;
  code?: string;
}

function sendChannels(client: RealtimeClient, type: "subscribe" | "unsubscribe", targets: string[]): void {
  if (targets.length === 0) return;
  // Wire shape is `{type, channels}`, not `RealtimeClient`'s `{type, payload}`
  // envelope -- see the module doc. The double cast is deliberate: this is
  // the one place in the app allowed to speak the gateway's actual protocol.
  client.send({ type, channels: targets } as unknown as RealtimeMessage);
}

function handleFrame(envelope: ChannelEnvelope, client: RealtimeClient, onPayload: (channel: string, payload: unknown) => void): void {
  if (envelope.type === "ping") {
    client.send({ type: "pong" } as unknown as RealtimeMessage);
    return;
  }
  if (envelope.type === "error") {
    logger.warn("market_channel_denied", { code: envelope.code, channel: envelope.channel });
    return;
  }
  if (typeof envelope.channel !== "string" || typeof envelope.data !== "string") return;
  try {
    onPayload(envelope.channel, JSON.parse(envelope.data) as unknown);
  } catch (error) {
    logger.warn("market_channel_payload_parse_failed", { error: String(error) });
  }
}

export function useMarketChannels(options: UseMarketChannelsOptions): UseMarketChannelsResult {
  const { channels, getAuthToken, enabled = true, onMessage } = options;
  const [status, setStatus] = useState<RealtimeStatus>("idle");
  const [messages, setMessages] = useState<Record<string, unknown>>({});
  const clientRef = useRef<RealtimeClient | null>(null);
  const subscribedRef = useRef<Set<string>>(new Set());
  const onMessageRef = useRef(onMessage);
  useEffect(() => {
    onMessageRef.current = onMessage;
  });

  const desired = channels.slice(0, MAX_CHANNELS_PER_CONNECTION);
  const isOverCap = channels.length > MAX_CHANNELS_PER_CONNECTION;
  const desiredKey = [...desired].sort().join(",");

  // A side effect (logging) belongs in an effect, not the render body -- the
  // render-body call fired on every re-render while over the cap, not only
  // when the cap was actually crossed (T1.5 review F10).
  useEffect(() => {
    if (isOverCap) {
      logger.warn("market_channels_capped", { requested: channels.length, cap: MAX_CHANNELS_PER_CONNECTION });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- log once when crossing the cap, not on every render while `channels.length` fluctuates above it
  }, [isOverCap]);

  useEffect(() => {
    if (!enabled) return;
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL;
    if (!wsUrl) {
      logger.warn("market_channels_disabled_missing_url", {});
      return;
    }

    const client = new RealtimeClient({
      url: wsUrl,
      getAuthToken,
      onStatusChange: (next) => {
        setStatus(next);
        // A fresh connection means the server has forgotten every previous
        // subscription -- reset so the next diff effect resends them all.
        if (next === "open") subscribedRef.current = new Set();
      },
      onMessage: (raw) => {
        handleFrame(raw as unknown as ChannelEnvelope, client, (channel, payload) => {
          setMessages((prev) => ({ ...prev, [channel]: payload }));
          onMessageRef.current?.(channel, payload);
        });
      },
    });
    clientRef.current = client;
    client.connect();

    return () => {
      client.close();
      clientRef.current = null;
      subscribedRef.current = new Set();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- getAuthToken is expected stable per caller
  }, [enabled]);

  useEffect(() => {
    const client = clientRef.current;
    if (!client || status !== "open") return;
    const current = subscribedRef.current;
    const toUnsubscribe = [...current].filter((channel) => !desired.includes(channel));
    const toSubscribe = desired.filter((channel) => !current.has(channel));

    sendChannels(client, "unsubscribe", toUnsubscribe);
    for (const channel of toUnsubscribe) current.delete(channel);
    sendChannels(client, "subscribe", toSubscribe);
    for (const channel of toSubscribe) current.add(channel);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `desired` is derived from `desiredKey`
  }, [desiredKey, status]);

  return { status, messages };
}
