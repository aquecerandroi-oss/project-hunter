/**
 * "Mesa spot/1" (T4.74-6, design `docs/design/spot1-lab-solana.md` §7) -- the
 * Lab's Binance signal executed on Solana/Jupiter by the same real wallet,
 * rendered inside the "Carteira real" band of `/meme/mesa`
 * (`wallet-summary-panel.tsx` sits directly above this one on the page --
 * kept a separate component here because the wallet's own 10 s poll and this
 * pista's data come from different reads: the wallet from `GET
 * /meme/live/wallet-summary`, this one from `LiveExecutorOut.spot1`, already
 * loaded once per page render alongside `GET /meme/live`). Server Component,
 * no interactivity, no invented number: a field the heartbeat never wrote is
 * `null`/absent, not zero.
 */
import type { VariantProps } from "class-variance-authority";

import { BrasiliaShort } from "@/components/time/brasilia-instant";
import { formatSol } from "@/components/meme/meme-format";
import { Badge, type badgeVariants } from "@/components/ui/badge";
import type { LiveExecutor } from "@/lib/api/meme-live-types";

import { truncateAddress } from "./live-format";
import { RealBadge } from "./real-confirm";
import { executorRefusalLabel } from "./refusal-labels";
import { formatSolSigned, pnlColorClass } from "./wallet-summary-format";

export type Spot1 = NonNullable<LiveExecutor["spot1"]>;
type Spot1OpenPosition = Spot1["open"][number];
type BadgeVariant = VariantProps<typeof badgeVariants>["variant"];

/** Design §4's three exit names -- a different, smaller vocabulary than `components/meme-desk/labels.ts`'s `MemeExitReason` (that one never had "stop"/"time"), so kept local rather than widening a shared file for one caller. */
const EXIT_REASON_LABEL: Record<string, string> = { stop: "stop (R ≤ -1)", target: "alvo (1,5R)", time: "prazo (horizonte) esgotado" };

function exitLabel(reason: string): string {
  return EXIT_REASON_LABEL[reason] ?? `saída: ${reason}`;
}

function formatR(value: string | null): string {
  if (value === null) return "sem amostra";
  const n = Number(value);
  return Number.isFinite(n) ? `${n >= 0 ? "+" : ""}${n.toFixed(2)}R` : `${value}R`;
}

function formatDurationS(seconds: number | null): string {
  if (seconds === null) return "sem leitura";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

function modeChip(mode: string): { label: string; variant: BadgeVariant } {
  if (mode === "on") return { label: "ligada", variant: "positive" };
  if (mode === "refuted") return { label: "refutada", variant: "negative" };
  if (mode === "cooldown") return { label: "pausa (cooldown)", variant: "warning" };
  if (mode.startsWith("inert:")) return { label: `inerte: ${mode.slice("inert:".length)}`, variant: "default" };
  return { label: `modo não previsto: ${mode}`, variant: "default" };
}

function OpenRow({ position }: { position: Spot1OpenPosition }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 border-b border-border py-1.5 text-xs last:border-0">
      <span className="font-mono text-fg">{position.market}</span>
      <span className="font-mono text-fg-subtle">{position.mint8}…</span>
      <span className="text-fg-subtle">
        <BrasiliaShort iso={position.entry_at} />
      </span>
      <span className="font-mono tabular-nums text-fg">{formatSol(position.sol_spent)}</span>
      <span className="font-mono tabular-nums text-fg">{position.mark_sol !== null ? formatSol(position.mark_sol) : "sem marca ainda"}</span>
      <span className={`font-mono tabular-nums ${pnlColorClass(position.r_now)}`}>{position.r_now !== null ? formatR(position.r_now) : "—"}</span>
      <span className="text-fg-muted">
        {formatDurationS(position.age_s)} de {formatDurationS(position.horizon_s)}
      </span>
      {position.mark_stale_s !== null && <span className="text-warning">marca envelhecida há {Math.round(position.mark_stale_s)} s</span>}
    </li>
  );
}

function ReasonCounts({ title, counts, label }: { title: string; counts: Record<string, number>; label: (reason: string) => string }) {
  const entries = Object.entries(counts);
  if (entries.length === 0) return null;
  return (
    <div>
      <h4 className="text-[11px] font-semibold uppercase text-fg-muted">{title}</h4>
      <ul className="text-xs text-fg-muted">
        {entries.map(([reason, count]) => (
          <li key={reason}>
            {label(reason)} × {count}
          </li>
        ))}
      </ul>
    </div>
  );
}

function RefutationMeter({ refutation }: { refutation: Spot1["refutation"] }) {
  const pct = refutation.threshold > 0 ? Math.min(100, Math.max(0, (refutation.trades / refutation.threshold) * 100)) : 0;
  const barColor = refutation.state === "refuted" ? "bg-red" : pct >= 70 ? "bg-warning" : "bg-green";
  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs text-fg-muted">
        Refutação: <span className="font-mono tabular-nums text-fg">{refutation.trades}</span> de <span className="font-mono tabular-nums text-fg">{refutation.threshold}</span> operações fechadas
        — estado <span className="font-mono text-fg">{refutation.state}</span>
      </p>
      <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Progresso até a regra de refutação" className="h-2 w-full overflow-hidden rounded-full bg-bg-overlay">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function ClosedStats({ closed }: { closed: Spot1["closed"] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div>
        <p className="text-[11px] font-medium uppercase text-fg-muted">Fechadas</p>
        <p className="font-mono text-base tabular-nums text-fg">{closed.n}</p>
      </div>
      <div>
        <p className="text-[11px] font-medium uppercase text-fg-muted">Σ R líquido</p>
        <p className={`font-mono text-base tabular-nums ${pnlColorClass(closed.sum_r_net)}`}>{formatR(closed.sum_r_net)}</p>
        <p className="text-[11px] text-fg-subtle">bruto {formatR(closed.sum_r_gross)}</p>
      </div>
      <div>
        <p className="text-[11px] font-medium uppercase text-fg-muted">PnL</p>
        <p className={`font-mono text-base tabular-nums ${pnlColorClass(closed.sum_pnl_sol)}`}>{formatSolSigned(closed.sum_pnl_sol)}</p>
      </div>
      <div>
        <p className="text-[11px] font-medium uppercase text-fg-muted">Expectância (R líq.)</p>
        <p className={`font-mono text-base tabular-nums ${pnlColorClass(closed.expectancy_r_net)}`}>{formatR(closed.expectancy_r_net)}</p>
      </div>
    </div>
  );
}

function Header({ mode }: { mode: string }) {
  const chip = modeChip(mode);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <RealBadge />
      <h3 className="text-sm font-semibold text-fg">Mesa spot/1</h3>
      <Badge variant={chip.variant}>{chip.label}</Badge>
    </div>
  );
}

export function Spot1Panel({ spot1 }: { spot1: Spot1 | null | undefined }) {
  if (!spot1) {
    return (
      <section className="flex flex-col gap-1 rounded-lg border border-dashed border-border bg-bg-elevated p-3">
        <h3 className="text-sm font-semibold text-fg-muted">Mesa spot/1 — ainda não ligada</h3>
        <p className="text-xs text-fg-muted">Este executor ainda não relata a pista spot/1 no heartbeat (build antigo, ou a pista nunca foi ligada).</p>
      </section>
    );
  }

  const lastEntriesTick = spot1.last_entries_tick_at;
  const lastExitsTick = spot1.last_exits_tick_at;
  const blocked = Object.entries(spot1.blocked_exits);

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border bg-bg-elevated p-3">
      <Header mode={spot1.mode} />
      <p className="text-xs text-fg-muted">
        estratégia <span className="font-mono text-fg">{spot1.strategy_version || "sem versão"}</span> · ficha <span className="font-mono tabular-nums text-fg">{formatSol(spot1.ticket_sol)}</span> ·
        até <span className="font-mono tabular-nums text-fg">{spot1.max_open}</span> abertas · {spot1.markets_enabled} mercado(s) ligado(s) · {spot1.signals_seen} sinal(is) visto(s) · {spot1.admitted}{" "}
        admitido(s)
      </p>

      <div>
        <h4 className="mb-1 text-[11px] font-semibold uppercase text-fg-muted">Abertas (spot/1)</h4>
        {spot1.open.length === 0 ? (
          <p className="text-sm text-fg-muted">Nenhuma posição spot/1 aberta agora.</p>
        ) : (
          <ul>
            {spot1.open.map((position) => (
              <OpenRow key={`${position.market}-${position.entry_at}`} position={position} />
            ))}
          </ul>
        )}
      </div>

      <ClosedStats closed={spot1.closed} />
      <RefutationMeter refutation={spot1.refutation} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <ReasonCounts title="Recusadas por motivo" counts={spot1.refused_by_reason} label={(reason) => executorRefusalLabel(reason) ?? `recusa: ${reason}`} />
        <ReasonCounts title="Saídas por motivo" counts={spot1.exits_by_reason} label={exitLabel} />
      </div>

      {blocked.length > 0 && (
        <div className="text-xs">
          <p className="font-medium text-warning">Saídas bloqueadas</p>
          <ul className="list-disc pl-4 text-fg">
            {blocked.map(([positionId, reason]) => (
              <li key={positionId}>
                posição {positionId.slice(0, 8)}: {executorRefusalLabel(reason) ?? reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-fg-subtle">
        {spot1.last_signature && <span>última assinatura {truncateAddress(spot1.last_signature)}</span>}
        {spot1.last_refusal && <span>última recusa: {executorRefusalLabel(spot1.last_refusal) ?? spot1.last_refusal}</span>}
        {lastEntriesTick && (
          <span>
            entradas em <BrasiliaShort iso={lastEntriesTick} />
          </span>
        )}
        {lastExitsTick && (
          <span>
            saídas em <BrasiliaShort iso={lastExitsTick} />
          </span>
        )}
      </div>
    </section>
  );
}
