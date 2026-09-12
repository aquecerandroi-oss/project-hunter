"use client";

import { Check, Copy } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { logger } from "@/lib/logger";

export interface ManualPlanBlockProps {
  /** `DeskRowOut.manual_plan` -- the loop's own Portuguese text, written at proposal time (T4.19), shown whole and never rephrased here. */
  plan: string;
  mint: string;
  /** The card's countdown to `expires_at` -- the "até HH:MM:SS" the plan's first sentence refers to. */
  countdown: string;
  expired: boolean;
}

type CopyState = "idle" | "copied" | "failed";

const COPY_FAILED = "não foi possível copiar — selecione o mint";

/**
 * "Plano para executar à mão" (T4.20): Everton runs the real test by hand in
 * the terminal following this text, so the block is the card's attention
 * state (`warning` tokens, docs/DESIGN.md §2) with the whole plan, the same
 * countdown the header shows and a one-tap copy of the mint. The clipboard
 * may refuse (insecure context, permission): the block says so and leaves
 * the full mint readable to select -- never a silent no-op.
 */
export function ManualPlanBlock({ plan, mint, countdown, expired }: ManualPlanBlockProps) {
  const headingId = useId();
  const [copy, setCopy] = useState<CopyState>("idle");

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(mint);
      setCopy("copied");
    } catch (error) {
      logger.warn("meme_manual_plan_copy_failed", { error: error instanceof Error ? error.message : String(error) });
      setCopy("failed");
    }
  }

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2 rounded-md border border-warning/40 bg-warning-soft p-3">
      <h4 id={headingId} className="text-xs font-medium uppercase tracking-wide text-warning">
        Plano para executar à mão
      </h4>
      <p className="whitespace-pre-wrap text-[13px] text-fg">{plan}</p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Button type="button" size="sm" variant="outline" onClick={() => void handleCopy()}>
          {copy === "copied" ? <Check className="size-4" /> : <Copy className="size-4" />}
          {copy === "copied" ? "Mint copiado" : "Copiar mint"}
        </Button>
        <code className="min-w-0 break-all font-mono text-[11px] text-fg-muted">{mint}</code>
        <span className={`ml-auto font-mono text-xs tabular-nums ${expired ? "text-fg-muted" : "text-fg"}`}>{countdown}</span>
      </div>
      {copy === "failed" && <p className="text-[11px] text-fg-muted">{COPY_FAILED}</p>}
    </section>
  );
}
