import Link from "next/link";

import { formatMemePct, formatSol } from "@/components/meme/meme-format";
import { BrasiliaShort } from "@/components/time/brasilia-instant";
import { Button } from "@/components/ui/button";
import type { MemeDeskRow } from "@/lib/api/meme-desk-types";

import { originLabel, quoteReasonLabel } from "./labels";
import { countdownLabel, formatMultiple } from "./meme-desk-format";

function truncate(address: string): string {
  return address.length <= 12 ? address : `${address.slice(0, 5)}…${address.slice(-5)}`;
}

function QuoteLine({ row }: { row: MemeDeskRow }) {
  const q = row.quote;
  if (!q.cost_sol && !q.mcap_sol) return <p className="text-[11px] text-fg-subtle">{quoteReasonLabel(q.reason)}</p>;
  return (
    <p className="text-[11px] text-fg-muted">
      {q.mcap_sol ? `mcap ${formatSol(q.mcap_sol, 2)}` : "mcap sem dado"}
      {q.curve_progress_pct ? ` · curva ${formatMemePct(q.curve_progress_pct)}` : ""}
      {q.cost_sol ? ` · custo ${formatSol(q.cost_sol)}` : ""}
      {q.fee_sol ? ` (taxa ${formatSol(q.fee_sol)})` : ""}
      {q.observed_at ? (
        <>
          {" "}
          · fotografia <BrasiliaShort iso={q.observed_at} />
        </>
      ) : null}
    </p>
  );
}

function SuggestedLine({ row }: { row: MemeDeskRow }) {
  const s = row.suggested;
  const parts = [
    s.size_sol ? formatSol(s.size_sol) : null,
    s.target_x ? `alvo ${formatMultiple(s.target_x)}` : null,
    s.trailing_pct ? `trailing ${s.trailing_pct}%` : null,
    s.max_hold_s !== null && s.max_hold_s !== undefined ? `espera ${s.max_hold_s} s` : null,
  ].filter((p): p is string => p !== null);
  return <p className="font-mono text-[11px] tabular-nums text-fg-muted">sugerido: {parts.length ? parts.join(" · ") : "sem sugestão registrada"}</p>;
}

function Header({ orgSlug, row, countdown, expired }: { orgSlug: string; row: MemeDeskRow; countdown: string; expired: boolean }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <div className="min-w-0">
        <Link href={`/${orgSlug}/meme/${row.mint}`} className="text-sm font-medium text-fg hover:underline">
          {row.token?.name ?? "(nome desconhecido)"}
        </Link>
        <span className="ml-2 text-[11px] text-fg-subtle">{row.token?.symbol ?? ""}</span>
        <span className="ml-2 font-mono text-[11px] text-fg-subtle">{truncate(row.mint)}</span>
      </div>
      <span className={`font-mono text-xs tabular-nums ${expired ? "text-red" : "text-warning"}`}>{countdown}</span>
    </div>
  );
}

function ReasonsLine({ row }: { row: MemeDeskRow }) {
  return (
    <p className="text-[11px] text-fg-muted">
      {originLabel(row.origin)} · motivo: {row.reasons.length ? row.reasons.map(String).join(", ") : "não informado"}
      {row.rule_set ? ` · conjunto ${row.rule_set.name} v${row.rule_set.version}` : ""}
    </p>
  );
}

interface ActionsProps {
  canOperate: boolean;
  blocked: string | null;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
}

/** Aprovar is off past the deadline or without the role; Recusar stays available past the deadline (a "no" is worth recording until the loop stamps `expired`). */
function Actions({ canOperate, blocked, busy, onApprove, onReject }: ActionsProps) {
  const roleReason = canOperate ? undefined : "Requer o papel Trader ou superior nesta organização.";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button type="button" size="sm" onClick={onApprove} disabled={busy || blocked !== null} title={blocked ?? undefined}>
        Aprovar
      </Button>
      <Button type="button" size="sm" variant="outline" onClick={onReject} disabled={busy || !canOperate} title={roleReason}>
        Recusar
      </Button>
      {blocked && <span className="text-[11px] text-fg-subtle">{blocked}</span>}
    </div>
  );
}

export interface ProposalCardProps {
  orgSlug: string;
  row: MemeDeskRow;
  nowMs: number;
  canOperate: boolean;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
}

/** One proposal awaiting the operator's call: countdown, why the loop proposed it, the quote and the two actions (contract §Tela). */
export function ProposalCard({ orgSlug, row, nowMs, canOperate, busy, onApprove, onReject }: ProposalCardProps) {
  const countdown = countdownLabel(row.expires_at, nowMs);
  const expired = countdown.startsWith("expirou");
  const blocked = !canOperate ? "Requer o papel Trader ou superior nesta organização." : expired ? "Prazo vencido — o laço marca como expirada." : null;
  return (
    <li className="flex flex-col gap-2 rounded-md border border-border p-3">
      <Header orgSlug={orgSlug} row={row} countdown={countdown} expired={expired} />
      <ReasonsLine row={row} />
      <QuoteLine row={row} />
      <SuggestedLine row={row} />
      <Actions canOperate={canOperate} blocked={blocked} busy={busy} onApprove={onApprove} onReject={onReject} />
    </li>
  );
}
