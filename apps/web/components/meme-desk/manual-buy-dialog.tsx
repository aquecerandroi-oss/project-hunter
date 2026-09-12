"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { fileManualProposalAction } from "@/lib/api/meme-desk-actions";
import { firstIssueMessage, manualBuyFormSchema, type ManualBuyFormValues, toManualBody } from "@/lib/api/meme-desk-form-schema";

import { memeDeskProblemMessage } from "./labels";
import { ParamsFields } from "./params-fields";

const EMPTY: ManualBuyFormValues = { mint: "", sizeSol: "", targetX: "", trailingPct: "", maxHoldS: "", note: "" };

interface ManualBuyFormProps {
  orgId: string;
  onFiled: () => void;
}

/** Mounted fresh per opening (`key`), so the `Idempotency-Key` is one per gesture and the fields start blank -- no invented default size. */
function ManualBuyForm({ orgId, onFiled }: ManualBuyFormProps) {
  const [values, setValues] = useState<ManualBuyFormValues>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());

  async function submit(): Promise<void> {
    setError(null);
    const parsed = manualBuyFormSchema.safeParse(values);
    if (!parsed.success) {
      setError(firstIssueMessage(parsed.error));
      return;
    }
    setSubmitting(true);
    try {
      const result = await fileManualProposalAction(orgId, idempotencyKeyRef.current, toManualBody(parsed.data));
      if (!result.ok) {
        setError(memeDeskProblemMessage(result.problem));
        return;
      }
      onFiled();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div>
        <label htmlFor="manual-buy-mint" className="mb-1 block text-xs font-medium text-fg-muted">
          Mint (pump.fun)
        </label>
        <Input
          id="manual-buy-mint"
          type="text"
          value={values.mint}
          onChange={(e) => setValues({ ...values, mint: e.target.value })}
          disabled={submitting}
          placeholder="cole o endereço do mint"
          className="w-full font-mono"
        />
        <p className="mt-1 text-[11px] text-fg-subtle">Só mints que o radar acompanha e ainda estão na curva.</p>
      </div>
      <ParamsFields idPrefix="manual-buy" values={values} onChange={(next) => setValues({ ...values, ...next })} disabled={submitting} />
      <p className="text-[11px] text-fg-subtle">Papel: a proposta nasce aprovada sob o conjunto do operador; o laço compra na próxima fotografia, não neste preço.</p>
      {error && <p className="text-sm text-red">{error}</p>}
      <div className="flex justify-end">
        <Button type="button" size="sm" onClick={() => void submit()} disabled={submitting}>
          {submitting ? "Registrando..." : "Registrar compra (papel)"}
        </Button>
      </div>
    </div>
  );
}

export interface ManualBuyDialogProps {
  orgId: string;
  canOperate: boolean;
}

/** "Comprar manual" (contract §Tela): mint + the same four parameters -> `POST /proposals/manual`. */
export function ManualBuyDialog({ orgId, canOperate }: ManualBuyDialogProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [openCount, setOpenCount] = useState(0);
  const blockReason = canOperate ? null : "Requer o papel Trader ou superior nesta organização.";

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        type="button"
        size="sm"
        variant="secondary"
        disabled={!canOperate}
        title={blockReason ?? undefined}
        onClick={() => {
          setOpenCount((n) => n + 1);
          setOpen(true);
        }}
      >
        Comprar manual
      </Button>
      {blockReason && <p className="text-[11px] text-fg-subtle">{blockReason}</p>}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <div className="border-b border-border p-4">
            <DialogTitle>Comprar manual (papel)</DialogTitle>
          </div>
          {open && (
            <ManualBuyForm
              key={openCount}
              orgId={orgId}
              onFiled={() => {
                setOpen(false);
                router.refresh();
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
