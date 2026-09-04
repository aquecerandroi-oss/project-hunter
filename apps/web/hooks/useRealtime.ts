"use client";

import { useEffect, useRef, useState } from "react";

import { logger } from "@/lib/logger";
import { RealtimeClient, type RealtimeMessage, type RealtimeStatus } from "@/lib/ws";

export interface UseRealtimeOptions {
  /** Logical channel name, e.g. `rt:radar` (docs/ARCHITECTURE.md §5.2). */
  channel: string;
  getAuthToken: () => Promise<string | null> | string | null;
  onMessage?: (message: RealtimeMessage) => void;
  /**
   * Defaults to `false`. In M0 no worker publishes on any `rt:*` channel
   * yet and the `api` WS gateway itself doesn't exist -- callers must not
   * flip this to `true` before the corresponding backend piece lands (M1+).
   */
  enabled?: boolean;
}

export interface UseRealtimeResult {
  status: RealtimeStatus;
}

/** The only sanctioned way for a client component to reach `lib/ws.ts` (enforced by ESLint). */
export function useRealtime(options: UseRealtimeOptions): UseRealtimeResult {
  const { channel, getAuthToken, onMessage, enabled = false } = options;
  const [status, setStatus] = useState<RealtimeStatus>("idle");
  const clientRef = useRef<RealtimeClient | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL;
    if (!wsUrl) {
      logger.warn("realtime_disabled_missing_url", { channel });
      return;
    }

    const client = new RealtimeClient({
      url: `${wsUrl}?channel=${encodeURIComponent(channel)}`,
      getAuthToken,
      onMessage,
      onStatusChange: setStatus,
    });
    clientRef.current = client;
    client.connect();

    return () => {
      client.close();
      clientRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- getAuthToken/onMessage are expected to be stable per caller
  }, [channel, enabled]);

  return { status };
}
