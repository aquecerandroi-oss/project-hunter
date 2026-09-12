"use server";

import { z } from "zod";

import { logger } from "@/lib/logger";
import { apiFetch } from "@/lib/server/api";
import { requireSession } from "@/lib/server/auth";

import {
  type MemeDeskApproveBody,
  type MemeDeskCommand,
  type MemeDeskManualBody,
  type MemeDeskProposalOut,
  type MemeDeskRejectBody,
  memeDeskBase,
} from "./meme-desk-types";
import { actionError, actionOk, ApiError, problemFromApiError, unauthenticatedProblem, validationProblem } from "./types";
import type { ActionResult } from "./types";

const IDEMPOTENCY_KEY_MIN_LENGTH = 8;
const IDEMPOTENCY_KEY_MAX_LENGTH = 128;

/** Sanity guards on the wire shape (the generated types are compile-time only) -- `.passthrough()` keeps every field the API sent. */
const proposalOutSchema = z.object({ row: z.object({ id: z.string(), status: z.string() }).passthrough() }).passthrough();
const commandOutSchema = z.object({ id: z.string(), command: z.string() }).passthrough();

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
 * One POST of the desk (T4.7, `routers/meme_desk.py`). `idempotencyKey` is
 * generated once per operator gesture (sheet opened, confirm shown) and
 * reused for every retry of that same gesture -- the same rule
 * `manual-orders-actions.ts` documents. Role (TRADER+) and every 409/422
 * (`meme-proposal-state-conflict`, `meme-bet-state-conflict`,
 * `meme-desk-refused` with a named reason, `idempotency-key-conflict`) come
 * back as `ActionResult.problem` unchanged; `components/meme-desk/labels.ts`
 * turns them into Portuguese.
 */
async function post<T>(path: string, idempotencyKey: string, body: unknown, schema: z.ZodTypeAny): Promise<ActionResult<T>> {
  const invalidKey = keyProblem(idempotencyKey);
  if (invalidKey) return actionError(invalidKey);

  const session = await requireSession();
  if (!session) return actionError(unauthenticatedProblem());

  try {
    const raw = await apiFetch<unknown>(path, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body ?? {}),
    });
    const parsed = schema.safeParse(raw);
    if (!parsed.success) {
      logger.error("meme_desk_response_shape_mismatch", { path, issues: parsed.error.issues });
      return actionError(shapeMismatchProblem());
    }
    return actionOk(raw as T);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}

/** `POST .../meme/proposals/{id}/approve` -- the operator's four parameters become `decision`. */
export async function approveProposalAction(orgId: string, proposalId: string, idempotencyKey: string, body: MemeDeskApproveBody): Promise<ActionResult<MemeDeskProposalOut>> {
  return post(`${memeDeskBase(orgId)}/proposals/${encodeURIComponent(proposalId)}/approve`, idempotencyKey, body, proposalOutSchema);
}

/** `POST .../meme/proposals/{id}/reject`. */
export async function rejectProposalAction(orgId: string, proposalId: string, idempotencyKey: string, body: MemeDeskRejectBody = {}): Promise<ActionResult<MemeDeskProposalOut>> {
  return post(`${memeDeskBase(orgId)}/proposals/${encodeURIComponent(proposalId)}/reject`, idempotencyKey, body, proposalOutSchema);
}

/** `POST .../meme/proposals/manual` -- a proposal born approved under `operator/1`, filled by the loop on the next snapshot. */
export async function fileManualProposalAction(orgId: string, idempotencyKey: string, body: MemeDeskManualBody): Promise<ActionResult<MemeDeskProposalOut>> {
  return post(`${memeDeskBase(orgId)}/proposals/manual`, idempotencyKey, body, proposalOutSchema);
}

/** `POST .../meme/bets/{id}/sell-now` -- 202: sold on the next snapshot, not at this price. */
export async function sellNowAction(orgId: string, betId: string, idempotencyKey: string): Promise<ActionResult<MemeDeskCommand>> {
  return post(`${memeDeskBase(orgId)}/bets/${encodeURIComponent(betId)}/sell-now`, idempotencyKey, {}, commandOutSchema);
}

/** `POST .../meme/proposals/{id}/cancel` -- only before a fill. */
export async function cancelProposalAction(orgId: string, proposalId: string, idempotencyKey: string): Promise<ActionResult<MemeDeskCommand>> {
  return post(`${memeDeskBase(orgId)}/proposals/${encodeURIComponent(proposalId)}/cancel`, idempotencyKey, {}, commandOutSchema);
}
