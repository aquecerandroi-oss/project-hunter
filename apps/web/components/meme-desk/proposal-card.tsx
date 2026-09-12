import Link from "next/link";

import { formatSol } from "@/components/meme/meme-format";
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
      {q.curve_progress_pct ? ` · curva ${formatQuoteProgress(q.curve_progress_pct)}` : ""}
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

/** The loop writes `curve_progress_pct` into the quote already as a percent ("25.8459"); `formatMemePct` expects a fraction, which printed "2,584.59 %" on the desk (12/09 12:17 BRT). */
function formatQuoteProgress(value: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(2)}%` : value;
}

/** T4.16: the 15-second clock's gate reads `meme_features_15s` instead of the closed-minute row; the minute series keeps its plain "regra x/y" text. */
const FAST_CLOCK_SERIES = "meme_features_15s_v1";

/** T4.10a proposals carry structured reasons (`{feature, value, window?, cap?}` or `{rule}`); `String(obj)` printed "[object Object]". */
export function reasonText(reason: unknown): string {
  if (typeof reason === "string") return reason;
  if (reason && typeof reason === "object") {
    const r = reason as Record<string, unknown>;
    if (typeof r.rule === "string") return r.series === FAST_CLOCK_SERIES ? `regra ${r.rule} · porta de 15 s` : `regra ${r.rule}`;
    const feature = typeof r.feature === "string" ? r.feature : "?";
    const value = r.value === undefined || r.value === null ? "" : String(r.value);
    const window = Array.isArray(r.window) ? ` (janela ${r.window.map(String).join("–")})` : "";
    const cap = r.cap === undefined || r.cap === null ? "" : ` (teto ${String(r.cap)})`;
    return `${feature} = ${value}${window}${cap}`;
  }
  return String(reason);
}

function ReasonsLine({ row }: { row: MemeDeskRow }) {
  return (
    <p className="text-[11px] text-fg-muted">
      {originLabel(row.origin)} · motivo: {row.reasons.length ? row.reasons.map(reasonText).join(" · ") : "não informado"}
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
  /** T4.17: `null` when the operator may open "Aprovar (REAL)" (role ok, deadline ok, executor `ligado`); otherwise the exact reason it is off. */
  realBlocked: string | null;
  onApproveReal: () => void;
}

/** Aprovar is off past the deadline or without the role; Recusar stays available past the deadline (a "no" is worth recording until the loop stamps `expired`). "Aprovar (REAL)" carries its own, separate gate (T4.17): the executor must be `ligado`, on top of the paper button's own conditions. */
function Actions({ canOperate, blocked, busy, onApprove, onReject, realBlocked, onApproveReal }: ActionsProps) {
  const roleReason = canOperate ? undefined : "Requer o papel Trader ou superior nesta organização.";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button type="button" size="sm" onClick={onApprove} disabled={busy || blocked !== null} title={blocked ?? undefined}>
        Aprovar
      </Button>
      <Button type="button" size="sm" variant="outline" onClick={onReject} disabled={busy || !canOperate} title={roleReason}>
        Recusar
      </Button>
      <Button type="button" size="sm" variant="destructive" onClick={onApproveReal} disabled={busy || realBlocked !== null} title={realBlocked ?? undefined}>
        Aprovar (REAL)
      </Button>
      {blocked && <span className="text-[11px] text-fg-subtle">{blocked}</span>}
      {!blocked && realBlocked && <span className="text-[11px] text-fg-subtle">{realBlocked}</span>}
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
  /** `true` only when the executor is `ligado` (heartbeat alive, its own flag on) AND the API's own flag is on -- `lib/api/meme-live-types.ts`'s `realActionsAvailable`. */
  realAvailable: boolean;
  onApproveReal: () => void;
}

/** One proposal awaiting the operator's call: countdown, why the loop proposed it, the quote and the actions (contract §Tela; "Aprovar (REAL)" per T4.17). */
export function ProposalCard({ orgSlug, row, nowMs, canOperate, busy, onApprove, onReject, realAvailable, onApproveReal }: ProposalCardProps) {
  const countdown = countdownLabel(row.expires_at, nowMs);
  const expired = countdown.startsWith("expirou");
  const blocked = !canOperate ? "Requer o papel Trader ou superior nesta organização." : expired ? "Prazo vencido — o laço marca como expirada." : null;
  const realBlocked = !canOperate
    ? "Requer o papel Trader ou superior nesta organização."
    : expired
      ? "Prazo vencido — o laço marca como expirada."
      : !realAvailable
        ? "O executor real não está ligado — veja o painel Executor real."
        : null;
  return (
    <li className="flex flex-col gap-2 rounded-md border border-border p-3">
      <Header orgSlug={orgSlug} row={row} countdown={countdown} expired={expired} />
      <ReasonsLine row={row} />
      <QuoteLine row={row} />
      <SuggestedLine row={row} />
      <Actions canOperate={canOperate} blocked={blocked} busy={busy} onApprove={onApprove} onReject={onReject} realBlocked={realBlocked} onApproveReal={onApproveReal} />
    </li>
  );
}
