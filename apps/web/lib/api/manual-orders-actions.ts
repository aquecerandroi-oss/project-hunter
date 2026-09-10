"use server";

import { logger } from "@/lib/logger";
import { apiFetch } from "@/lib/server/api";
import { requireSession } from "@/lib/server/auth";

import {
  manualOrderDetailSchema,
  manualOrderOutSchema,
  manualOrderRequestBodySchema,
  manualOrdersPath,
  type ManualOrderDetail,
  type ManualOrderOut,
  type ManualOrderRequestBody,
} from "./manual-orders-types";
import { actionError, actionOk, ApiError, problemFromApiError, unauthenticatedProblem, validationProblem } from "./types";
import type { ActionResult } from "./types";

const IDEMPOTENCY_KEY_MIN_LENGTH = 8;
const IDEMPOTENCY_KEY_MAX_LENGTH = 128;

function shapeMismatchProblem(): { type: string; title: string; status: number; detail: string } {
  return {
    type: "https://hunter.dev/problems/unexpected-response",
    title: "Resposta inesperada",
    status: 502,
    detail: "A resposta da API não veio no formato esperado.",
  };
}

/**
 * `POST .../order-requests` (T3.72/T3.68/T3.72c, `routers/orders.py::
 * file_manual_order_route`) -- files one manual paper order, always `202`.
 * `idempotencyKey` is generated once per form submission
 * (`manual-order-form.tsx`, `crypto.randomUUID()`) and reused for every retry
 * of that same submission, never regenerated on retry -- a fresh key on
 * retry would defeat the header's entire purpose (a second real order on a
 * network hiccup).
 *
 * Shape (`manualOrderRequestBodySchema`) and role (TRADER+) are re-checked
 * here for fast, honest feedback, but the API is the only real authority --
 * a 403 (`insufficient-role`), 409 (`idempotency-key-conflict`/
 * `wallet-not-open`) or 422 (`order-refused`, reason in `detail`) it returns
 * is mapped to `ActionResult.problem` unchanged (`manual-order-labels.ts`
 * turns `problem.type`/`detail` into Portuguese in the component, never
 * here).
 */
export async function fileManualOrderAction(
  orgId: string,
  portfolioId: string,
  idempotencyKey: string,
  input: ManualOrderRequestBody,
): Promise<ActionResult<ManualOrderOut>> {
  const parsedBody = manualOrderRequestBodySchema.safeParse(input);
  if (!parsedBody.success) {
    return actionError(validationProblem(parsedBody.error.issues[0]?.message ?? "Dados inválidos."));
  }
  if (idempotencyKey.length < IDEMPOTENCY_KEY_MIN_LENGTH || idempotencyKey.length > IDEMPOTENCY_KEY_MAX_LENGTH) {
    return actionError(validationProblem("Chave de idempotência inválida."));
  }

  const session = await requireSession();
  if (!session) return actionError(unauthenticatedProblem());

  try {
    const raw = await apiFetch<unknown>(manualOrdersPath(orgId, portfolioId), {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(parsedBody.data),
    });
    const parsed = manualOrderOutSchema.safeParse(raw);
    if (!parsed.success) {
      logger.error("manual_order_response_shape_mismatch", { issues: parsed.error.issues });
      return actionError(shapeMismatchProblem());
    }
    return actionOk(parsed.data);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}

/**
 * `GET .../order-requests/{request_id}` -- polled every 2s by
 * `manual-order-form.tsx` while `status === "pending"`, for up to 60s (brief
 * item 1). A client component cannot call `apiFetch` directly (ESLint
 * boundary, `lib/server/api.ts` is `"server-only"`), hence this Server
 * Action wrapper -- same shape as `fileManualOrderAction` above.
 */
export async function pollManualOrderAction(
  orgId: string,
  portfolioId: string,
  requestId: string,
): Promise<ActionResult<ManualOrderDetail>> {
  const session = await requireSession();
  if (!session) return actionError(unauthenticatedProblem());

  try {
    const raw = await apiFetch<unknown>(`${manualOrdersPath(orgId, portfolioId)}/${requestId}`);
    const parsed = manualOrderDetailSchema.safeParse(raw);
    if (!parsed.success) {
      logger.error("manual_order_detail_shape_mismatch", { issues: parsed.error.issues });
      return actionError(shapeMismatchProblem());
    }
    return actionOk(parsed.data);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}
