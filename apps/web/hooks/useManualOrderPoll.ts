"use client";

import { useEffect, useRef, useState } from "react";

import { pollManualOrderAction } from "@/lib/api/manual-orders-actions";
import type { ManualOrderDetail, ManualOrderOut } from "@/lib/api/manual-orders-types";
import { logger } from "@/lib/logger";

const POLL_INTERVAL_MS = 2_000;
const POLL_TIMEOUT_MS = 60_000;

export interface ManualOrderPollState {
  /** The freshest known snapshot of the request -- the optimistic `202` body until a poll lands. */
  order: ManualOrderOut | ManualOrderDetail;
  /** `true` once `order.status === "decided"` -- polling has stopped for good. */
  settled: boolean;
  /** `true` when 60s passed with no decision -- polling stopped, the request may still resolve later (visible on the list/on reload), never claimed as failed. */
  timedOut: boolean;
  /** Set only on a real fetch failure (never on a normal "still pending") -- polling stops. */
  error: string | null;
}

/** What the interval's own async callbacks write -- keyed to the request it belongs to, so a stale value from a previous `filed` can never leak into a render for a newer one (see the render-time guard below, not a `setState` reset in the effect). */
interface PollMeta {
  forRequestId: string;
  latest: ManualOrderOut | ManualOrderDetail;
  timedOut: boolean;
  error: string | null;
}

/**
 * Polls `GET .../orders/{request_id}` every 2s while `status === "pending"`,
 * for up to 60s (brief item 1: "poll the GET every 2s for <= 60s"). Starts
 * fresh whenever `filed` changes identity (a new submission) and stops on
 * decision, timeout, unmount, or a fetch error -- never leaves a stray
 * interval running past any of those.
 *
 * `meta` is written to ONLY from inside the interval's own async callbacks
 * (react-hooks' own sanctioned case: "subscribe to an external system,
 * calling setState in a callback when it changes") -- never synchronously at
 * the top of the effect to "reset on prop change" (`react-hooks/set-state-in-effect`
 * flags exactly that). Whether a given `meta` still describes the current
 * `filed` is instead a plain comparison done during render (`forRequestId`),
 * so switching to a new `filed` needs no reset write at all.
 */
export function useManualOrderPoll(orgId: string, portfolioId: string, filed: ManualOrderOut | null): ManualOrderPollState | null {
  const [meta, setMeta] = useState<PollMeta | null>(null);
  const requestIdRef = useRef<string | null>(filed?.request_id ?? null);

  useEffect(() => {
    requestIdRef.current = filed?.request_id ?? null;
    if (!filed || filed.status === "decided") return undefined;

    const startedAt = Date.now();
    const interval = window.setInterval(() => {
      const thisRequestId = filed.request_id;
      if (Date.now() - startedAt >= POLL_TIMEOUT_MS) {
        if (requestIdRef.current !== thisRequestId) return;
        window.clearInterval(interval);
        setMeta((prev) => ({
          forRequestId: thisRequestId,
          latest: prev && prev.forRequestId === thisRequestId ? prev.latest : filed,
          timedOut: true,
          error: null,
        }));
        return;
      }
      pollManualOrderAction(orgId, portfolioId, thisRequestId)
        .then((result) => {
          if (requestIdRef.current !== thisRequestId) return;
          if (!result.ok) {
            logger.warn("manual_order_poll_failed", { reason: result.problem.detail ?? result.problem.title });
            window.clearInterval(interval);
            setMeta({ forRequestId: thisRequestId, latest: filed, timedOut: false, error: result.problem.detail ?? result.problem.title });
            return;
          }
          const decided = result.data.status === "decided";
          setMeta({ forRequestId: thisRequestId, latest: result.data, timedOut: false, error: null });
          if (decided) window.clearInterval(interval);
        })
        .catch((error: unknown) => {
          if (requestIdRef.current !== thisRequestId) return;
          logger.warn("manual_order_poll_threw", { error: String(error) });
          window.clearInterval(interval);
          setMeta({ forRequestId: thisRequestId, latest: filed, timedOut: false, error: "erro desconhecido" });
        });
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [filed, orgId, portfolioId]);

  if (!filed) return null;
  const current = meta && meta.forRequestId === filed.request_id ? meta : null;
  const order = current?.latest ?? filed;
  return {
    order,
    settled: order.status === "decided",
    timedOut: current?.timedOut ?? false,
    error: current?.error ?? null,
  };
}
