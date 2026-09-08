"use client";

import { Badge } from "@/components/ui/badge";
import { formatPrice } from "@/components/markets/format";
import { LabAsOf } from "@/components/lab/lab-as-of";
import { LabExcursions } from "@/components/lab/lab-excursions";
import { LabSignalDetail } from "@/components/lab/lab-signal-detail";
import { ResultChip, TrackingStateChip } from "@/components/lab/lab-signal-chips";
import { formatR, reasonLabel, signColorClass } from "@/components/lab/lab-format";
import { MONEY_TOOLTIP, moneyForRow, priceAndTime, saidaText, usdtToBrl, type MoneyOrReason, type MoneyRuler } from "@/components/lab/lab-money";
import { ResultBadge } from "@/components/lab/lab-result-badge";
import { formatMoneyRange, MONEY_DIVERGENCE_NOTE, notionalRangeUsdt, pnlRangeUsdt, type MoneyRange } from "@/components/lab/lab-signal-divergence";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { formatBrlSigned, formatPct, formatUsdtSigned } from "@/lib/format";

export interface LabSignalPanelProps {
  signal: SignalListItemOut | null;
  versionLabel: string;
  ruler: MoneyRuler;
  /**
   * Every signal in this operation's own identity group (brief T3.38) --
   * length 1 outside a merged row, more than 1 when sibling versions decided
   * the exact same bar/entry/exit. The panel is the "expanding ... lists the
   * per-version signal ids" side of the brief's either/or (the row itself
   * never changes height, which the virtualization math in
   * `hooks/useVirtualizedRows.ts` depends on).
   */
  siblingSignals?: SignalListItemOut[];
  versionLabelFor?: (id: string) => string;
}

/** Rendered only when `siblingSignals` spans more than one version (brief T3.38 item 1: "expanding the row (or the side panel) lists the per-version signal ids"). */
function SiblingSignalsBlock({ members, versionLabelFor }: { members: SignalListItemOut[]; versionLabelFor: (id: string) => string }) {
  if (members.length <= 1) return null;
  return (
    <div className="rounded-md border border-border bg-bg-overlay p-3 text-xs">
      <p className="mb-1.5 text-fg-muted">
        {members.length} versões irmãs decidiram esta mesma operação (mesma barra, entrada e saída) -- cada uma com seu próprio sinal:
      </p>
      <ul className="flex flex-col gap-1">
        {members.map((member) => (
          <li key={member.signal_id} className="flex flex-wrap items-center gap-1.5">
            <Badge variant={member.purpose === "paper" ? "info" : "outline"} className="px-1.5 py-0 text-[11px]">
              {versionLabelFor(member.strategy_version_id)}
            </Badge>
            <span className="font-mono text-fg-subtle">{member.signal_id}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Finding 2 of the T3.38 review: a merged group whose members still disagree
 * on money (should now be impossible once T3.38c-api's `stop` fix is live)
 * needs the real range instead of `signal`'s (the group's primary) own
 * value standing in for the whole group. Split out of `SignalMoneyBlock`
 * itself so that function's own cyclomatic complexity stays under the lint
 * config's budget.
 */
function moneyRangesForSiblings(siblingSignals: SignalListItemOut[], ruler: MoneyRuler): { pnlRange: MoneyRange | null; notionalRange: MoneyRange | null } {
  if (siblingSignals.length <= 1) return { pnlRange: null, notionalRange: null };
  return { pnlRange: pnlRangeUsdt(siblingSignals, ruler), notionalRange: notionalRangeUsdt(siblingSignals, ruler) };
}

/** "Quantia simulada" cell text -- the range (+note) when siblings diverge, else the ordinary single figure or its honest reason. */
function notionalCellText(notionalRange: MoneyRange | null, notionalUsdt: MoneyOrReason): string {
  if (notionalRange) return `${formatMoneyRange(notionalRange)} (faixa)`;
  if (notionalUsdt.value !== null) return formatUsdtSigned(notionalUsdt.value);
  return reasonLabel(notionalUsdt.reason ?? "");
}

/** "Resultado" cell content -- same divergence rule as `notionalCellText`, kept as its own component (rather than inline JSX) for the same complexity-budget reason. */
function ResultCellContent({ pnlRange, pnlUsdt, pnlBrl }: { pnlRange: MoneyRange | null; pnlUsdt: MoneyOrReason; pnlBrl: number | null }) {
  if (pnlRange) return <span className="font-mono tabular-nums text-warning">{formatMoneyRange(pnlRange)} (faixa)</span>;
  return (
    <>
      <ResultBadge pnlUsdt={pnlUsdt.value} />
      {pnlUsdt.value !== null ? (
        <span className="font-mono tabular-nums text-fg">
          {formatUsdtSigned(pnlUsdt.value)}
          {pnlBrl !== null && <span className="text-fg-muted"> ({formatBrlSigned(pnlBrl)})</span>}
        </span>
      ) : (
        <span className="text-fg-muted">{reasonLabel(pnlUsdt.reason ?? "sem motivo informado")}</span>
      )}
    </>
  );
}

/**
 * The money block Everton asked for (brief T3.17): what the signal entered
 * with, what it left with, profit or loss -- above the research block below,
 * which stays unchanged (raw levels, R, excursions, funding). Every number
 * here is derived from the one declared ruler (`lab-money.ts`), never a
 * second, silently different computation.
 */
function SignalMoneyBlock({ signal, ruler, siblingSignals }: { signal: SignalListItemOut; ruler: MoneyRuler; siblingSignals: SignalListItemOut[] }) {
  const { pnlUsdt, notionalUsdt, pctMove } = moneyForRow(signal, ruler);
  const pnlBrl = pnlUsdt.value !== null ? usdtToBrl(pnlUsdt.value, ruler) : null;
  const { pnlRange, notionalRange } = moneyRangesForSiblings(siblingSignals, ruler);

  return (
    <dl title={MONEY_TOOLTIP} className="grid grid-cols-2 gap-2 rounded-md border border-border bg-bg-overlay p-3 text-xs sm:grid-cols-3">
      <div>
        <dt className="text-fg-muted">Entrou</dt>
        <dd className="font-mono tabular-nums text-fg">{priceAndTime(signal.virtual_entry, signal.entry_ts)}</dd>
      </div>
      <div>
        <dt className="text-fg-muted">Saiu</dt>
        <dd className="font-mono tabular-nums text-fg">{saidaText(signal)}</dd>
      </div>
      <div>
        <dt className="text-fg-muted">Variação</dt>
        <dd className={`font-mono tabular-nums ${pctMove === null ? "text-fg-muted" : pctMove >= 0 ? "text-green" : "text-red"}`}>
          {pctMove !== null ? formatPct(pctMove) : "--"}
        </dd>
      </div>
      <div>
        <dt className="text-fg-muted">Quantia simulada</dt>
        <dd className="font-mono tabular-nums text-fg" title={notionalRange ? MONEY_DIVERGENCE_NOTE : undefined}>
          {notionalCellText(notionalRange, notionalUsdt)}
        </dd>
      </div>
      <div className="col-span-2 sm:col-span-1">
        <dt className="text-fg-muted">Resultado</dt>
        <dd className="flex items-center gap-1.5" title={pnlRange ? MONEY_DIVERGENCE_NOTE : undefined}>
          <ResultCellContent pnlRange={pnlRange} pnlUsdt={pnlUsdt} pnlBrl={pnlBrl} />
        </dd>
      </div>
    </dl>
  );
}

/**
 * The "painel lateral/expansível" from brief S3b: full detail for one
 * selected signal (never all ~200 rows at once), including the excursions
 * and an on-demand envelope fetch. A row-height-changing accordion would
 * break the fixed row height the virtualization math in
 * `hooks/useVirtualizedRows.ts` depends on, so this lives beside the table
 * (below it on mobile, `lg:` beside it) instead.
 */
export function LabSignalPanel({ signal, versionLabel, ruler, siblingSignals = [], versionLabelFor }: LabSignalPanelProps) {
  if (!signal) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-6 text-sm text-fg-muted">
        Selecione um sinal na tabela (clique ou Enter) para ver o detalhe completo.
      </div>
    );
  }

  const r = formatR(signal.r_multiple, signal.r_multiple_reason);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-bg-elevated p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-semibold text-fg">{signal.market}</span>
        <span className="text-xs text-fg-muted">{versionLabel}</span>
        <TrackingStateChip state={signal.tracking_state} reason={signal.no_entry_reason ?? signal.censored_reason} />
        <ResultChip result={signal.result} />
      </div>
      <p className="text-xs text-fg-muted">
        Decisão: <LabAsOf iso={signal.decision_at} /> -- barra de referência:{" "}
        <LabAsOf iso={signal.source_bar_close} />
      </p>

      <SignalMoneyBlock signal={signal} ruler={ruler} siblingSignals={siblingSignals} />

      {versionLabelFor && <SiblingSignalsBlock members={siblingSignals} versionLabelFor={versionLabelFor} />}

      <p className="mt-1 text-[11px] font-semibold uppercase text-fg-muted">Detalhe de pesquisa</p>
      <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-fg-muted">Referência</dt>
          <dd className="font-mono tabular-nums text-fg">{formatPrice(signal.reference_price)}</dd>
        </div>
        <div>
          <dt className="text-fg-muted">Stop</dt>
          <dd className="font-mono tabular-nums text-fg">{formatPrice(signal.stop)}</dd>
        </div>
        <div>
          <dt className="text-fg-muted">Alvo</dt>
          <dd className="font-mono tabular-nums text-fg">{formatPrice(signal.target1)}</dd>
        </div>
        <div>
          <dt className="text-fg-muted">Entrada virtual</dt>
          <dd className="font-mono tabular-nums text-fg">{formatPrice(signal.virtual_entry)}</dd>
        </div>
        <div>
          <dt className="text-fg-muted">Saída</dt>
          <dd className="font-mono tabular-nums text-fg">{formatPrice(signal.exit_price)}</dd>
        </div>
        <div>
          <dt className="text-fg-muted">R líquido</dt>
          <dd className={`font-mono tabular-nums ${r.isValue ? signColorClass(signal.r_multiple) : "text-fg-muted"}`}>
            {r.text}
          </dd>
        </div>
        <div>
          <dt className="text-fg-muted">R ex-funding</dt>
          <dd className={`font-mono tabular-nums ${signal.r_ex_funding !== null ? signColorClass(signal.r_ex_funding) : "text-fg-muted"}`}>
            {signal.r_ex_funding !== null ? `${signal.r_ex_funding}R` : "--"}
          </dd>
        </div>
        {signal.no_entry_reason && (
          <div>
            <dt className="text-fg-muted">Sem entrada</dt>
            <dd className="text-fg">{reasonLabel(signal.no_entry_reason)}</dd>
          </div>
        )}
        {signal.censored_reason && (
          <div>
            <dt className="text-fg-muted">Censurado</dt>
            <dd className="text-fg">{reasonLabel(signal.censored_reason)}</dd>
          </div>
        )}
      </dl>

      <div>
        <p className="mb-1 text-xs font-semibold text-fg-muted">Excursões (MFE/MAE)</p>
        <LabExcursions excursions={signal.excursions} />
      </div>

      <LabSignalDetail
        signalId={signal.signal_id}
        market={signal.market}
        strategyVersionId={signal.strategy_version_id}
        cohort={signal.cohort}
      />
    </div>
  );
}
