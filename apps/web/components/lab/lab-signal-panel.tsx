"use client";

import { formatPrice } from "@/components/markets/format";
import { LabAsOf } from "@/components/lab/lab-as-of";
import { LabExcursions } from "@/components/lab/lab-excursions";
import { LabSignalDetail } from "@/components/lab/lab-signal-detail";
import { ResultChip, TrackingStateChip } from "@/components/lab/lab-signal-chips";
import { formatR, reasonLabel, signColorClass } from "@/components/lab/lab-format";
import type { SignalListItemOut } from "@/lib/api/lab-types";

export interface LabSignalPanelProps {
  signal: SignalListItemOut | null;
  versionLabel: string;
}

/**
 * The "painel lateral/expansível" from brief S3b: full detail for one
 * selected signal (never all ~200 rows at once), including the excursions
 * and an on-demand envelope fetch. A row-height-changing accordion would
 * break the fixed row height the virtualization math in
 * `hooks/useVirtualizedRows.ts` depends on, so this lives beside the table
 * (below it on mobile, `lg:` beside it) instead.
 */
export function LabSignalPanel({ signal, versionLabel }: LabSignalPanelProps) {
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
