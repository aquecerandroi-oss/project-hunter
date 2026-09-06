import { Badge } from "@/components/ui/badge";
import { reasonLabel } from "@/components/lab/lab-format";
import type { VersionCounts } from "@/lib/api/lab-types";

export interface LabFunnelProps {
  counts: VersionCounts;
}

/**
 * The funnel of counts (brief S3b): emitted -> entradas -> sem entrada por
 * motivo -> ativos -> encerrados por resultado -> censurados por motivo.
 * `decisions` is always `null` (`Evaluation.state` is never durable,
 * `counts.decisions_reason`) -- shown as its own reason line, not folded
 * into `signals_emitted` as if the two counted the same thing.
 */
export function LabFunnel({ counts }: LabFunnelProps) {
  const noEntryReasons = Object.entries(counts.no_entry.by_reason).filter(([, n]) => n > 0);
  const terminalResults = Object.entries(counts.terminal.by_result).filter(([, n]) => n > 0);
  const censoredReasons = Object.entries(counts.censored.by_reason).filter(([, n]) => n > 0);

  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-3">
      <div>
        <dt className="text-fg-muted">Avaliações (decisões)</dt>
        <dd className="font-mono tabular-nums text-fg-muted">{reasonLabel(counts.decisions_reason)}</dd>
      </div>
      <div>
        <dt className="text-fg-muted">Sinais emitidos</dt>
        <dd className="font-mono tabular-nums text-fg">{counts.signals_emitted}</dd>
      </div>
      <div>
        <dt className="text-fg-muted">Pendentes de entrada</dt>
        <dd className="font-mono tabular-nums text-fg">{counts.pending_entry}</dd>
      </div>
      <div>
        <dt className="text-fg-muted">Entradas</dt>
        <dd className="font-mono tabular-nums text-fg">{counts.entered}</dd>
      </div>
      <div>
        <dt className="text-fg-muted">Ativos</dt>
        <dd className="font-mono tabular-nums text-fg">{counts.active}</dd>
      </div>
      <div>
        <dt className="text-fg-muted">Funding não apurável</dt>
        <dd className="font-mono tabular-nums text-fg">{counts.funding_not_settleable}</dd>
      </div>
      <div className="col-span-full">
        <dt className="text-fg-muted">Sem entrada ({counts.no_entry.total}) por motivo</dt>
        <dd className="mt-1 flex flex-wrap gap-1.5">
          {noEntryReasons.length === 0 ? (
            <span className="text-fg-subtle">nenhum</span>
          ) : (
            noEntryReasons.map(([reason, n]) => (
              <Badge key={reason} variant="default">{`${reasonLabel(reason)}: ${n}`}</Badge>
            ))
          )}
        </dd>
      </div>
      <div className="col-span-full">
        <dt className="text-fg-muted">Encerrados ({counts.terminal.total}) por resultado</dt>
        <dd className="mt-1 flex flex-wrap gap-1.5">
          {terminalResults.length === 0 ? (
            <span className="text-fg-subtle">nenhum</span>
          ) : (
            terminalResults.map(([result, n]) => (
              <Badge key={result} variant="default">{`${result}: ${n}`}</Badge>
            ))
          )}
        </dd>
      </div>
      <div className="col-span-full">
        <dt className="text-fg-muted">Censurados ({counts.censored.total}) por motivo</dt>
        <dd className="mt-1 flex flex-wrap gap-1.5">
          {censoredReasons.length === 0 ? (
            <span className="text-fg-subtle">nenhum</span>
          ) : (
            censoredReasons.map(([reason, n]) => (
              <Badge key={reason} variant="default">{`${reasonLabel(reason)}: ${n}`}</Badge>
            ))
          )}
        </dd>
      </div>
    </dl>
  );
}
