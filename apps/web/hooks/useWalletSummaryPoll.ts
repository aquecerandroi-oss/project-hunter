"use client";

import { useEffect, useRef, useState } from "react";

import { pollWalletSummaryAction } from "@/lib/api/meme-live-wallet-actions";
import type { WalletSummary } from "@/lib/api/meme-live-wallet-types";
import { logger } from "@/lib/logger";

const POLL_INTERVAL_MS = 10_000;

export interface WalletSummaryPollState {
  /** The freshest snapshot this hook has fetched, or `null` before the first response lands. */
  summary: WalletSummary | null;
  /** Set only on a real fetch failure -- the previous `summary` (if any) stays on screen, never cleared by a transient error. */
  reason: string | null;
}

/**
 * Polls `GET .../meme/live/wallet-summary` every 10 s (brief T4.57: "a
 * carteira precisa estar mostrando o resultado real agora"), pausing while
 * the tab is hidden -- the `AutoRefresh` convention
 * (`components/auto-refresh.tsx`), reimplemented here because this panel
 * polls its own endpoint independently of the page's 5 s refresh instead of
 * riding it. Fetches once immediately on mount, then on the interval; a
 * failure keeps the last good `summary` on screen and only updates `reason`
 * -- an honest reload note, never a screen that goes blank on one dropped
 * request.
 */
export function useWalletSummaryPoll(orgId: string): WalletSummaryPollState {
  const [summary, setSummary] = useState<WalletSummary | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const orgIdRef = useRef(orgId);

  useEffect(() => {
    orgIdRef.current = orgId;
    let cancelled = false;

    async function tick(): Promise<void> {
      if (document.visibilityState !== "visible") return;
      try {
        const result = await pollWalletSummaryAction(orgIdRef.current);
        if (cancelled) return;
        if (!result.ok) {
          logger.warn("wallet_summary_poll_failed", { reason: result.problem.detail ?? result.problem.title });
          setReason(result.problem.detail ?? result.problem.title);
          return;
        }
        setSummary(result.data);
        setReason(null);
      } catch (error) {
        if (cancelled) return;
        logger.warn("wallet_summary_poll_threw", { error: String(error) });
        setReason("erro desconhecido");
      }
    }

    void tick();
    const interval = window.setInterval(() => void tick(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [orgId]);

  return { summary, reason };
}
