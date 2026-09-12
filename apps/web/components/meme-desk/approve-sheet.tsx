"use client";

import { useRef, useState } from "react";

import { formatSol } from "@/components/meme/meme-format";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { approveProposalAction } from "@/lib/api/meme-desk-actions";
import { deskParamsFormSchema, type DeskParamsFormValues, firstIssueMessage, formValuesFromSuggested, toApproveBody } from "@/lib/api/meme-desk-form-schema";
import type { MemeDeskRow } from "@/lib/api/meme-desk-types";

import { memeDeskProblemMessage, quoteReasonLabel } from "./labels";
import { ParamsFields } from "./params-fields";

interface ApproveFormProps {
  orgId: string;
  row: MemeDeskRow;
  onApproved: () => void;
}

/**
 * Mounted with `key={row.id}` by `ApproveSheet`, so every opening gets fresh
 * state: the fields pre-filled from the loop's `suggested` (contract §Tela)
 * and ONE `Idempotency-Key` for this gesture, reused across retries of the
 * same submission and never across two different proposals
 * (`manual-order-form.tsx`'s rule).
 */
function ApproveForm({ orgId, row, onApproved }: ApproveFormProps) {
  const [values, setValues] = useState<DeskParamsFormValues>(() => formValuesFromSuggested(row.suggested));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());
  const cap = row.rule_set?.max_sol_per_bet ?? null;

  async function submit(): Promise<void> {
    setError(null);
    const parsed = deskParamsFormSchema.safeParse(values);
    if (!parsed.success) {
      setError(firstIssueMessage(parsed.error));
      return;
    }
    setSubmitting(true);
    try {
      const result = await approveProposalAction(orgId, row.id, idempotencyKeyRef.current, toApproveBody(parsed.data));
      if (!result.ok) {
        setError(memeDeskProblemMessage(result.problem));
        return;
      }
      onApproved();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 overflow-y-auto p-4">
      <div className="text-xs text-fg-muted">
        <p className="text-sm font-medium text-fg">{row.token?.name ?? "(nome desconhecido)"}</p>
        <p className="break-all font-mono text-[11px] text-fg-subtle">{row.mint}</p>
        <p className="mt-1">
          {row.quote.cost_sol ? (
            <>
              custo cotado {formatSol(row.quote.cost_sol)} {row.quote.fee_sol ? `(taxa ${formatSol(row.quote.fee_sol)})` : ""} para {row.quote.size_sol ? formatSol(row.quote.size_sol) : "o tamanho sugerido"}
            </>
          ) : (
            quoteReasonLabel(row.quote.reason)
          )}
        </p>
        {cap && <p className="mt-1">teto por aposta do conjunto: {formatSol(cap)}</p>}
      </div>

      <ParamsFields idPrefix={`approve-${row.id}`} values={values} onChange={setValues} disabled={submitting} />

      <p className="text-[11px] text-fg-subtle">Papel: o laço compra na próxima fotografia da curva, não neste preço, e aplica os tetos do conjunto por cima.</p>

      {error && <p className="text-sm text-red">{error}</p>}

      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" onClick={() => void submit()} disabled={submitting}>
          {submitting ? "Aprovando..." : "Aprovar compra (papel)"}
        </Button>
      </div>
    </div>
  );
}

export interface ApproveSheetProps {
  orgId: string;
  row: MemeDeskRow | null;
  onOpenChange: (open: boolean) => void;
  onApproved: () => void;
}

/** The approval sheet (contract §Tela): four parameters pre-filled from `suggested`, editable, one primary action. */
export function ApproveSheet({ orgId, row, onOpenChange, onApproved }: ApproveSheetProps) {
  return (
    <Sheet open={row !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="max-w-md">
        <SheetHeader>
          <SheetTitle>Aprovar compra (papel)</SheetTitle>
        </SheetHeader>
        {row && <ApproveForm key={row.id} orgId={orgId} row={row} onApproved={onApproved} />}
      </SheetContent>
    </Sheet>
  );
}
