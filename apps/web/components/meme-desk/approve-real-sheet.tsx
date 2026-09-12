"use client";

import { useRef, useState } from "react";

import { realActionProblemMessage } from "@/components/meme-live/labels";
import { RealSummary, SizeMatchField, sizeMatches } from "@/components/meme-live/real-confirm";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { LiveExecutor } from "@/lib/api/meme-live-types";
import { approveProposalAction } from "@/lib/api/meme-desk-actions";
import { deskParamsFormSchema, type DeskParamsFormValues, firstIssueMessage, formValuesFromSuggested, toApproveBody } from "@/lib/api/meme-desk-form-schema";
import type { MemeDeskRow } from "@/lib/api/meme-desk-types";

import { ParamsFields } from "./params-fields";

function tickerLine(row: MemeDeskRow): string {
  const name = row.token?.name ?? "(nome desconhecido)";
  const symbol = row.token?.symbol ? ` (${row.token.symbol})` : "";
  const mint = row.mint.length <= 12 ? row.mint : `${row.mint.slice(0, 5)}…${row.mint.slice(-5)}`;
  return `${name}${symbol} · ${mint}`;
}

type Step = "params" | "confirm";

interface ApproveRealFormProps {
  orgId: string;
  row: MemeDeskRow;
  executor: LiveExecutor | null;
  onApproved: () => void;
}

/**
 * Mounted with `key={row.id}` by `ApproveRealSheet`, so every opening starts
 * fresh (contract §Tela's pattern): step (a) the four parameters, prefilled
 * from the loop's `suggested` and still editable; step (b) the summary plus
 * the typed-size gate before the red "Assinar e enviar (REAL)" unlocks. One
 * `Idempotency-Key` for the whole gesture, reused across retries of the same
 * submission, dropped the moment the operator steps back to edit a value.
 */
function ApproveRealForm({ orgId, row, executor, onApproved }: ApproveRealFormProps) {
  const [step, setStep] = useState<Step>("params");
  const [values, setValues] = useState<DeskParamsFormValues>(() => formValuesFromSuggested(row.suggested));
  const [typedSize, setTypedSize] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());

  function continueToConfirm(): void {
    setError(null);
    const parsed = deskParamsFormSchema.safeParse(values);
    if (!parsed.success) {
      setError(firstIssueMessage(parsed.error));
      return;
    }
    setStep("confirm");
  }

  async function submit(): Promise<void> {
    setError(null);
    const parsed = deskParamsFormSchema.safeParse(values);
    if (!parsed.success) {
      setError(firstIssueMessage(parsed.error));
      setStep("params");
      return;
    }
    setSubmitting(true);
    try {
      const result = await approveProposalAction(orgId, row.id, idempotencyKeyRef.current, toApproveBody(parsed.data, "live"));
      if (!result.ok) {
        setError(realActionProblemMessage(result.problem));
        return;
      }
      onApproved();
    } finally {
      setSubmitting(false);
    }
  }

  if (step === "params") {
    return (
      <div className="flex flex-col gap-4 overflow-y-auto p-4">
        <p className="text-xs text-fg-muted">Revise os quatro parâmetros antes de confirmar com dinheiro real.</p>
        <ParamsFields idPrefix={`approve-real-${row.id}`} values={values} onChange={setValues} disabled={submitting} />
        {error && <p className="text-sm text-red">{error}</p>}
        <div className="flex justify-end">
          <Button type="button" size="sm" variant="destructive" onClick={continueToConfirm} disabled={submitting}>
            Continuar
          </Button>
        </div>
      </div>
    );
  }

  const parsed = deskParamsFormSchema.safeParse(values);
  const sizeSol = parsed.success ? parsed.data.sizeSol : "";
  return (
    <div className="flex flex-col gap-4 overflow-y-auto p-4">
      <RealSummary tickerLine={tickerLine(row)} sizeSol={sizeSol} targetX={values.targetX} trailingPct={values.trailingPct} maxHoldS={values.maxHoldS} executor={executor} />
      <SizeMatchField id={`approve-real-size-${row.id}`} expected={sizeSol} value={typedSize} onChange={setTypedSize} disabled={submitting} />
      {error && <p className="text-sm text-red">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="outline" onClick={() => setStep("params")} disabled={submitting}>
          Voltar
        </Button>
        <Button type="button" size="sm" variant="destructive" onClick={() => void submit()} disabled={submitting || !sizeMatches(sizeSol, typedSize)}>
          {submitting ? "Enviando..." : "Assinar e enviar (REAL)"}
        </Button>
      </div>
    </div>
  );
}

export interface ApproveRealSheetProps {
  orgId: string;
  row: MemeDeskRow | null;
  executor: LiveExecutor | null;
  onOpenChange: (open: boolean) => void;
  onApproved: () => void;
}

/** "Aprovar (REAL)" (T4.17 deliverable 2): the double-confirmed sibling of `ApproveSheet`, only ever opened when the executor is `ligado` (the card's own gate). */
export function ApproveRealSheet({ orgId, row, executor, onOpenChange, onApproved }: ApproveRealSheetProps) {
  return (
    <Sheet open={row !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="max-w-md">
        <SheetHeader>
          <SheetTitle className="text-red">Aprovar (REAL)</SheetTitle>
        </SheetHeader>
        {row && <ApproveRealForm key={row.id} orgId={orgId} row={row} executor={executor} onApproved={onApproved} />}
      </SheetContent>
    </Sheet>
  );
}
