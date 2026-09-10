"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ManualOrderFiledStatus } from "@/components/portfolio/manual-order-filed-status";
import { ManualOrderMarketField } from "@/components/portfolio/manual-order-market-field";
import { ManualOrderStopField } from "@/components/portfolio/manual-order-stop-field";
import { manualOrderProblemMessage } from "@/components/portfolio/manual-order-labels";
import { useManualOrderPoll } from "@/hooks/useManualOrderPoll";
import { fileManualOrderAction } from "@/lib/api/manual-orders-actions";
import { manualOrderFormShapeSchema, validateStopAgainstMarket } from "@/lib/api/manual-order-form-schema";
import type { SpotMarketOption } from "@/lib/api/markets-actions";
import type { ManualOrderOut, ManualOrderRequestBody } from "@/lib/api/manual-orders-types";

/** Pure shape/geometry validation for one submit attempt -- pulled out of the component so `ManualOrderForm` itself stays under the lint config's per-function complexity budget. */
type SubmitValidation = { ok: true; body: ManualOrderRequestBody } | { ok: false; message: string };

function buildSubmission(market: SpotMarketOption | null, stop: string, requestedNotional: string, maxStopDistancePct: string | null): SubmitValidation {
  if (!market) return { ok: false, message: "Selecione um mercado SPOT." };

  const stopCheck = validateStopAgainstMarket(stop || "0", market.last_price, maxStopDistancePct);
  if (!stopCheck.ok) return { ok: false, message: stopCheck.message ?? "Stop inválido." };

  const parsed = manualOrderFormShapeSchema.safeParse({ marketId: market.id, direction: "long", stop, requestedNotional });
  if (!parsed.success) return { ok: false, message: parsed.error.issues[0]?.message ?? "Dados inválidos." };

  return {
    ok: true,
    body: {
      market_id: parsed.data.marketId,
      direction: parsed.data.direction,
      stop: parsed.data.stop,
      requested_notional: parsed.data.requestedNotional === "" ? null : parsed.data.requestedNotional,
    },
  };
}

export interface ManualOrderFormProps {
  orgId: string;
  portfolioId: string;
  /** `RiskLimitsPresetOut.max_stop_distance_pct` (docs/RISK_ENGINE.md §2) -- `null` when the limits read itself failed; the distance hint just does not render, never guesses a cap. */
  maxStopDistancePct: string | null;
  /** Called once the filed order's decision is known, so the parent can `router.refresh()` the requests table (T3.72 item 2). */
  onSettled: () => void;
}

/**
 * The "Nova ordem paper" form body (brief item 1). Direction is fixed to
 * `"long"` -- SPOT executes buys only until the engine says otherwise
 * (docs/RISK_ENGINE.md §2, `max_leverage: 1`); `"short"` is shown, disabled,
 * with the reason, never hidden (a trader should see the modality exists and
 * why it is off, not wonder if it was forgotten).
 */
export function ManualOrderForm({ orgId, portfolioId, maxStopDistancePct, onSettled }: ManualOrderFormProps) {
  const router = useRouter();
  const [market, setMarket] = useState<SpotMarketOption | null>(null);
  const [stop, setStop] = useState("");
  const [requestedNotional, setRequestedNotional] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [filedOrder, setFiledOrder] = useState<ManualOrderOut | null>(null);

  // One key per SUBMISSION, reused only across retries of that SAME
  // submission (e.g. a network error before a response ever arrived --
  // `handleSubmit` runs again with the same body, and the API must see the
  // same key to treat it as a retry, not a new order). "Enviar outra ordem"
  // (`resetForRetry`, below) is a *new* submission from the trader's point of
  // view -- reusing the key there while the body differs would 409
  // `order_replay_conflict` (the API remembers the key's original body), so
  // `resetForRetry` regenerates it there instead of waiting for a remount.
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());
  // Guards `onSettled` to fire exactly once per settlement, not on every
  // re-render while `settled` stays true.
  const notifiedRef = useRef(false);

  const poll = useManualOrderPoll(orgId, portfolioId, filedOrder);
  const stopCheck = validateStopAgainstMarket(stop || "0", market?.last_price ?? null, maxStopDistancePct);
  // The 202 body itself can already carry `decision` (brief: "202
  // `decision`: `null | RiskDecision`" when decided at filing time); once the
  // poll confirms `decided`, `poll.order` is the freshest snapshot and is
  // what the render below reads from directly -- `filedOrder` stays only the
  // key that started the poll, never re-read for its own `decision` once a
  // fresher one exists.
  const settled = poll?.settled ?? false;

  useEffect(() => {
    if (settled && !notifiedRef.current) {
      notifiedRef.current = true;
      onSettled();
    }
  }, [settled, onSettled]);

  /** "Enviar outra ordem": a new submission, not a retry of the last one -- fresh key, blank fields. */
  function resetForRetry(): void {
    idempotencyKeyRef.current = crypto.randomUUID();
    notifiedRef.current = false;
    setFiledOrder(null);
    setFormError(null);
    setMarket(null);
    setStop("");
    setRequestedNotional("");
  }

  async function handleSubmit(): Promise<void> {
    setFormError(null);
    const submission = buildSubmission(market, stop, requestedNotional, maxStopDistancePct);
    if (!submission.ok) {
      setFormError(submission.message);
      return;
    }

    setSubmitting(true);
    try {
      const result = await fileManualOrderAction(orgId, portfolioId, idempotencyKeyRef.current, submission.body);
      if (!result.ok) {
        setFormError(manualOrderProblemMessage(result.problem));
        return;
      }
      setFiledOrder(result.data);
      if (result.data.status === "decided") onSettled();
    } finally {
      setSubmitting(false);
    }
  }

  if (filedOrder) {
    return <ManualOrderFiledStatus filedOrder={filedOrder} poll={poll} onRetry={resetForRetry} onClose={() => router.refresh()} />;
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <div>
        <label className="mb-1 block text-xs font-medium text-fg-muted">Mercado SPOT</label>
        <ManualOrderMarketField value={market} onChange={setMarket} disabled={submitting} />
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-fg-muted">Direção</label>
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="default" disabled className="pointer-events-none">
            Comprado (long)
          </Button>
          <Button type="button" size="sm" variant="outline" disabled title="SPOT: só compra">
            Vendido (short)
          </Button>
        </div>
        <p className="mt-1 text-[11px] text-fg-subtle">SPOT: só compra -- venda a descoberto não é suportada pelo motor hoje.</p>
      </div>

      <ManualOrderStopField value={stop} onChange={setStop} disabled={submitting} check={stopCheck} maxStopDistancePct={maxStopDistancePct} />

      <div>
        <label htmlFor="manual-order-notional" className="mb-1 block text-xs font-medium text-fg-muted">
          Notional máximo (opcional)
        </label>
        <Input
          id="manual-order-notional"
          type="text"
          inputMode="decimal"
          value={requestedNotional}
          onChange={(e) => setRequestedNotional(e.target.value)}
          placeholder="Sem teto (o motor dimensiona)"
          disabled={submitting}
          className="w-full"
        />
        <p className="mt-1 text-[11px] text-fg-subtle">Um teto, nunca uma meta -- o motor pode aprovar um tamanho menor.</p>
      </div>

      {formError && <p className="text-sm text-red">{formError}</p>}

      <div className="flex justify-end">
        <Button type="button" size="sm" onClick={handleSubmit} disabled={submitting || !market}>
          {submitting ? "Enviando..." : "Enviar ordem"}
        </Button>
      </div>
    </div>
  );
}
