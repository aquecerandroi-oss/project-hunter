"use client";

import type { ReactNode } from "react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { ManualOrderForm } from "@/components/portfolio/manual-order-form";

export interface ManualOrderSectionProps {
  orgId: string;
  portfolioId: string;
  canTrade: boolean;
  walletOpenReason: string | null;
  killSwitchReason: string | null;
  /**
   * `riskProfileGateReason(riskLimits.preset)` (T3.72d) -- the wallet-level
   * banner's own sentence (`risk-profile-banner.tsx`), repeated here: the
   * execution-worker admits nothing while it is set (`risk_profile_missing`/
   * `_invalid`/`_diverged`, `hunter_execution_worker.risk_profile`, T3.69b),
   * so the button must say why alongside the wallet-open and kill-switch
   * reasons, never leave a trader to file a request the engine will only
   * ever leave pending.
   */
  riskProfileReason: string | null;
  maxStopDistancePct: string | null;
  /**
   * The requests table/empty-state, rendered by `portfolio/page.tsx` (a
   * Server Component: `ManualOrdersTable`/`PortfolioProposalsEmpty` have no
   * interactivity of their own, CLAUDE.md's "Server Components by default")
   * and passed through here as a slot -- this file stays `"use client"` only
   * for the dialog/form, never pulling the table into the client bundle.
   */
  children: ReactNode;
}

/**
 * "Nova ordem paper" action + the requests table (brief items 1-2). Gating
 * is layered, each with its own visible reason (never a bare disabled
 * button): role (TRADER+) first, then the wallet's own open state, then the
 * kill switch, then the linked risk profile (T3.72d) -- all four read from
 * GETs the screen already has, never a new source of truth. The button
 * stays visible and disabled (not hidden) for a VIEWER, so a member without
 * the role still sees the capability exists and why it is off, matching
 * `manual-order-form.tsx`'s own "short" treatment.
 */
export function ManualOrderSection({
  orgId,
  portfolioId,
  canTrade,
  walletOpenReason,
  killSwitchReason,
  riskProfileReason,
  maxStopDistancePct,
  children,
}: ManualOrderSectionProps) {
  const [open, setOpen] = useState(false);

  const blockReason = !canTrade
    ? "Requer o papel Trader ou superior nesta organização."
    : (walletOpenReason ?? killSwitchReason ?? riskProfileReason);
  const canOpen = blockReason === null;

  return (
    <div className="flex flex-col gap-3">
      {/* No heading here on purpose: `ManualOrdersTable`/`PortfolioProposalsEmpty`
          (the `children` slot below) already carry the "Propostas (ordens
          manuais)" heading -- a second one here would just repeat it. */}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <div className="flex flex-col items-end gap-1">
          <Button type="button" size="sm" disabled={!canOpen} onClick={() => setOpen(true)} title={blockReason ?? undefined}>
            Nova ordem paper
          </Button>
          {blockReason && <p className="text-[11px] text-fg-subtle">{blockReason}</p>}
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <div className="border-b border-border p-4">
            <DialogTitle>Nova ordem paper</DialogTitle>
          </div>
          {open && (
            <ManualOrderForm
              orgId={orgId}
              portfolioId={portfolioId}
              maxStopDistancePct={maxStopDistancePct}
              onSettled={() => {
                /* the SSR requests table below refreshes on the trader's own
                   "Fechar" click (`router.refresh()`, `manual-order-form.tsx`)
                   or on the next `AutoRefresh` tick -- nothing to do here. */
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      {children}
    </div>
  );
}
