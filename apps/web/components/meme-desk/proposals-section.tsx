"use client";

import type { Problem } from "@hunter/shared-types";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { BrasiliaShort } from "@/components/time/brasilia-instant";
import { Button } from "@/components/ui/button";
import { useAgeTicker } from "@/hooks/useAgeTicker";
import { cancelProposalAction, rejectProposalAction } from "@/lib/api/meme-desk-actions";
import type { MemeDeskRow, MemeLoopState } from "@/lib/api/meme-desk-types";

import { ApproveSheet } from "./approve-sheet";
import { memeDeskProblemMessage } from "./labels";
import { emptyProposalsLabel, loopStateLabel, minutesSinceNewestProposal } from "./meme-desk-format";
import { ProposalCard } from "./proposal-card";

/** The structural shape of every `ActionResult<T>` (`lib/api/types.ts` is `"server-only"`; a client component types the outcome by shape). */
type Outcome = { ok: true } | { ok: false; problem: Problem };

export interface ProposalsSectionProps {
  orgId: string;
  orgSlug: string;
  proposals: MemeDeskRow[];
  awaitingFill: MemeDeskRow[];
  allRows: MemeDeskRow[];
  loop: MemeLoopState;
  serverNow: string;
  canOperate: boolean;
}

/**
 * "Propostas" (contract §Tela): the loop's proposals awaiting the
 * operator's call, with a live countdown (`useAgeTicker` anchored to the
 * API's `server_now`), plus the ones already approved and waiting for the
 * next snapshot (cancellable until then). Reject/cancel are one tap with
 * their own fresh `Idempotency-Key`; approve opens the sheet.
 */
export function ProposalsSection({ orgId, orgSlug, proposals, awaitingFill, allRows, loop, serverNow, canOperate }: ProposalsSectionProps) {
  const router = useRouter();
  const { now } = useAgeTicker(serverNow);
  const [sheetRow, setSheetRow] = useState<MemeDeskRow | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(id: string, action: () => Promise<Outcome>): Promise<void> {
    setError(null);
    setBusyId(id);
    try {
      const result = await action();
      if (!result.ok) {
        setError(memeDeskProblemMessage(result.problem));
        return;
      }
      router.refresh();
    } finally {
      setBusyId(null);
    }
  }

  const loopState = loopStateLabel(loop, now);
  const emptyLabel = emptyProposalsLabel(loopState, minutesSinceNewestProposal(allRows, now));

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-fg">Propostas</h2>
      {proposals.length === 0 ? (
        <p className="rounded-md border border-border p-4 text-sm text-fg-muted">{emptyLabel}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {proposals.map((row) => (
            <ProposalCard
              key={row.id}
              orgSlug={orgSlug}
              row={row}
              nowMs={now}
              canOperate={canOperate}
              busy={busyId === row.id}
              onApprove={() => setSheetRow(row)}
              onReject={() => void run(row.id, () => rejectProposalAction(orgId, row.id, crypto.randomUUID()))}
            />
          ))}
        </ul>
      )}

      {awaitingFill.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Aprovadas — aguardando a próxima fotografia</h3>
          <ul className="flex flex-col gap-2">
            {awaitingFill.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3 text-xs">
                <span className="min-w-0">
                  <Link href={`/${orgSlug}/meme/${row.mint}`} className="text-sm font-medium text-fg hover:underline">
                    {row.token?.name ?? "(nome desconhecido)"}
                  </Link>
                  <span className="ml-2 text-fg-muted">
                    aprovada {row.decided_at ? <BrasiliaShort iso={row.decided_at} /> : "—"} · o laço compra na próxima fotografia (até 3 min; senão vira não preenchida)
                  </span>
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!canOperate || busyId === row.id}
                  title={!canOperate ? "Requer o papel Trader ou superior nesta organização." : undefined}
                  onClick={() => void run(row.id, () => cancelProposalAction(orgId, row.id, crypto.randomUUID()))}
                >
                  Cancelar
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <p className="text-sm text-red">{error}</p>}

      <ApproveSheet
        orgId={orgId}
        row={sheetRow}
        onOpenChange={(open) => {
          if (!open) setSheetRow(null);
        }}
        onApproved={() => {
          setSheetRow(null);
          router.refresh();
        }}
      />
    </section>
  );
}
