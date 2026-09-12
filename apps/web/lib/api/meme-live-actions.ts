"use server";

import { z } from "zod";

import { logger } from "@/lib/logger";
import { apiFetch } from "@/lib/server/api";
import { requireSession } from "@/lib/server/auth";

import { type SellNowResult, memeLiveBase } from "./meme-live-types";
import { actionError, actionOk, ApiError, problemFromApiError, unauthenticatedProblem, validationProblem } from "./types";
import type { ActionResult } from "./types";

const IDEMPOTENCY_KEY_MIN_LENGTH = 8;
const IDEMPOTENCY_KEY_MAX_LENGTH = 128;

/** Sanity guard on the wire shape (the generated types are compile-time only) -- `.passthrough()` keeps every field the API sent, same convention as `meme-desk-actions.ts`. */
const sellNowOutSchema = z.object({ position_id: z.string(), status: z.string(), already_requested: z.boolean() }).passthrough();

function shapeMismatchProblem(): { type: string; title: string; status: number; detail: string } {
  return {
    type: "https://hunter.dev/problems/unexpected-response",
    title: "Resposta inesperada",
    status: 502,
    detail: "A resposta da API não veio no formato esperado.",
  };
}

function keyProblem(idempotencyKey: string): ReturnType<typeof validationProblem> | null {
  if (idempotencyKey.length < IDEMPOTENCY_KEY_MIN_LENGTH || idempotencyKey.length > IDEMPOTENCY_KEY_MAX_LENGTH) {
    return validationProblem("Chave de idempotência inválida.");
  }
  return null;
}

/**
 * `POST .../meme/live/positions/{id}/sell-now` (T4.14/T4.17, TRADER+,
 * `Idempotency-Key`) -- the real executor's own sell-now, the same
 * one-`Idempotency-Key`-per-gesture pattern as `meme-desk-actions.ts`'s
 * `sellNowAction` on the paper ledger. 202 even on a replay of the same key
 * (`already_requested`): the executor sells on its next pass, at the curve's
 * price then, never at the mark shown now. `components/meme-live/labels.ts`
 * turns every 404/409/403 into Portuguese.
 */
export async function sellNowLiveAction(orgId: string, positionId: string, idempotencyKey: string): Promise<ActionResult<SellNowResult>> {
  const invalidKey = keyProblem(idempotencyKey);
  if (invalidKey) return actionError(invalidKey);

  const session = await requireSession();
  if (!session) return actionError(unauthenticatedProblem());

  try {
    const raw = await apiFetch<unknown>(`${memeLiveBase(orgId)}/positions/${encodeURIComponent(positionId)}/sell-now`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({}),
    });
    const parsed = sellNowOutSchema.safeParse(raw);
    if (!parsed.success) {
      logger.error("meme_live_response_shape_mismatch", { path: "sell-now", issues: parsed.error.issues });
      return actionError(shapeMismatchProblem());
    }
    return actionOk(raw as SellNowResult);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}
