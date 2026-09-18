"use server";

import { z } from "zod";

import { logger } from "@/lib/logger";
import { apiFetch } from "@/lib/server/api";
import { requireSession } from "@/lib/server/auth";

import { memeLiveWalletSummaryPath, type WalletSummary } from "./meme-live-wallet-types";
import { actionError, actionOk, ApiError, problemFromApiError, unauthenticatedProblem } from "./types";
import type { ActionResult } from "./types";

/** Sanity guard on the wire shape (the generated types are compile-time only) -- `.passthrough()` keeps every field the API sent, same convention as `meme-live-actions.ts`. */
const walletSummarySchema = z
  .object({
    server_now: z.string(),
    executor_status: z.string(),
    now: z.object({}).passthrough(),
    today: z.object({}).passthrough(),
    all_time: z.object({}).passthrough(),
    closed_today: z.array(z.unknown()),
    open: z.array(z.unknown()),
  })
  .passthrough();

function shapeMismatchProblem(): { type: string; title: string; status: number; detail: string } {
  return {
    type: "https://hunter.dev/problems/unexpected-response",
    title: "Resposta inesperada",
    status: 502,
    detail: "A resposta da API não veio no formato esperado.",
  };
}

/**
 * `GET .../meme/live/wallet-summary` (T4.57) -- polled every 10 s by
 * `useWalletSummaryPoll` (`wallet-summary-panel.tsx`). A client component
 * cannot call `apiFetch` directly (ESLint boundary, `lib/server/api.ts` is
 * `"server-only"`), hence this Server Action wrapper -- same shape as
 * `meme-live-actions.ts`'s `sellNowLiveAction`.
 */
export async function pollWalletSummaryAction(orgId: string): Promise<ActionResult<WalletSummary>> {
  const session = await requireSession();
  if (!session) return actionError(unauthenticatedProblem());

  try {
    const raw = await apiFetch<unknown>(memeLiveWalletSummaryPath(orgId));
    const parsed = walletSummarySchema.safeParse(raw);
    if (!parsed.success) {
      logger.error("meme_live_wallet_summary_shape_mismatch", { issues: parsed.error.issues });
      return actionError(shapeMismatchProblem());
    }
    return actionOk(raw as WalletSummary);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}
