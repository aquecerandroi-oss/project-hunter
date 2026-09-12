"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { realActionProblemMessage } from "@/components/meme-live/labels";
import { RealSummary, SizeMatchField, sizeMatches } from "@/components/meme-live/real-confirm";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { LiveExecutor } from "@/lib/api/meme-live-types";
import { fileManualProposalAction } from "@/lib/api/meme-desk-actions";
import { firstIssueMessage, manualBuyFormSchema, type ManualBuyFormValues, toManualBody } from "@/lib/api/meme-desk-form-schema";

import { memeDeskProblemMessage } from "./labels";
import { ParamsFields } from "./params-fields";

const EMPTY: ManualBuyFormValues = { mint: "", sizeSol: "", targetX: "", trailingPct: "", maxHoldS: "", note: "" };

function shortMint(mint: string): string {
  return mint.length <= 12 ? mint : `${mint.slice(0, 5)}…${mint.slice(-5)}`;
}

type Step = "params" | "confirm-real";

interface ManualBuyFormProps {
  orgId: string;
  liveAvailable: boolean;
  executor: LiveExecutor | null;
  onFiled: () => void;
}

/** Mounted fresh per opening (`key`), so the `Idempotency-Key` is one per gesture and the fields start blank -- no invented default size. Registrar (papel) files immediately; Registrar (REAL) -- T4.17, only enabled when the executor is `ligado` -- moves to a second, double-confirmed step before it ever posts `mode: "live"`. */
function ManualBuyForm({ orgId, liveAvailable, executor, onFiled }: ManualBuyFormProps) {
  const [step, setStep] = useState<Step>("params");
  const [values, setValues] = useState<ManualBuyFormValues>(EMPTY);
  const [typedSize, setTypedSize] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());

  function parse() {
    return manualBuyFormSchema.safeParse(values);
  }

  async function submitPaper(): Promise<void> {
    setError(null);
    const parsed = parse();
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

  function continueToRealConfirm(): void {
    setError(null);
    const parsed = parse();
    if (!parsed.success) {
      setError(firstIssueMessage(parsed.error));
      return;
    }
    setStep("confirm-real");
  }

  async function submitReal(): Promise<void> {
    setError(null);
    const parsed = parse();
    if (!parsed.success) {
      setError(firstIssueMessage(parsed.error));
      setStep("params");
      return;
    }
    setSubmitting(true);
    try {
      const result = await fileManualProposalAction(orgId, idempotencyKeyRef.current, toManualBody(parsed.data, "live"));
      if (!result.ok) {
        setError(realActionProblemMessage(result.problem));
        return;
      }
      onFiled();
    } finally {
      setSubmitting(false);
    }
  }

  if (step === "confirm-real") {
    const parsed = parse();
    const sizeSol = parsed.success ? parsed.data.sizeSol : "";
    return (
      <div className="flex flex-col gap-4 p-4">
        <RealSummary tickerLine={`(mint colado) · ${shortMint(values.mint)}`} sizeSol={sizeSol} targetX={values.targetX} trailingPct={values.trailingPct} maxHoldS={values.maxHoldS} executor={executor} />
        <SizeMatchField id="manual-buy-real-size" expected={sizeSol} value={typedSize} onChange={setTypedSize} disabled={submitting} />
        {error && <p className="text-sm text-red">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => setStep("params")} disabled={submitting}>
            Voltar
          </Button>
          <Button type="button" size="sm" variant="destructive" onClick={() => void submitReal()} disabled={submitting || !sizeMatches(sizeSol, typedSize)}>
            {submitting ? "Enviando..." : "Assinar e enviar (REAL)"}
          </Button>
        </div>
      </div>
    );
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
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" size="sm" onClick={() => void submitPaper()} disabled={submitting}>
          {submitting ? "Registrando..." : "Registrar compra (papel)"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="destructive"
          onClick={continueToRealConfirm}
          disabled={submitting || !liveAvailable}
          title={liveAvailable ? undefined : "O executor real não está ligado — veja o painel Executor real."}
        >
          Registrar (REAL)
        </Button>
      </div>
    </div>
  );
}

export interface ManualBuyDialogProps {
  orgId: string;
  canOperate: boolean;
  /** T4.17: `true` only when the real executor is `ligado` -- gates the "Registrar (REAL)" button inside the form. */
  liveAvailable?: boolean;
  executor?: LiveExecutor | null;
}

/** "Comprar manual" (contract §Tela): mint + the same four parameters -> `POST /proposals/manual`, paper or -- T4.17, double-confirmed -- REAL. */
export function ManualBuyDialog({ orgId, canOperate, liveAvailable = false, executor = null }: ManualBuyDialogProps) {
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
            <DialogTitle>Comprar manual</DialogTitle>
          </div>
          {open && (
            <ManualBuyForm
              key={openCount}
              orgId={orgId}
              liveAvailable={liveAvailable}
              executor={executor}
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
