import { Badge } from "@/components/ui/badge";

/**
 * T1.5b joint decision #5: three distinct facts, never fused into one dot
 * or one badge -- snapshot (a photo taken once), connection (the browser's
 * own socket to the realtime gateway) and per-component freshness (age vs.
 * the API's own `stale_after_ms`). Plus a fourth, separate state: "sem
 * verificação" (the check itself never ran) is not the same as "indisponível"
 * (it ran and failed) -- `components/layout/topbar.tsx`'s `dotState`.
 */
export function StalenessShowcase() {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-xs uppercase tracking-wide text-fg-muted">Qualidade por componente (quality-badge.tsx)</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <Badge variant="positive" className="gap-1.5">
            <span className="size-1.5 rounded-full bg-green" aria-hidden="true" />
            OK
          </Badge>
          <Badge variant="warning">atrasado 12s</Badge>
          <Badge variant="negative">gap</Badge>
          <Badge variant="default">sem dado</Badge>
        </div>
      </div>

      <div>
        <p className="text-xs uppercase tracking-wide text-fg-muted">Verificação do sistema (topbar.tsx)</p>
        <div className="mt-2 flex flex-wrap gap-3 text-sm text-fg-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-green" aria-hidden="true" />
            Sistema operacional
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-warning" aria-hidden="true" />
            Sistema degradado
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-red" aria-hidden="true" />
            Sistema indisponível
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-fg-subtle" aria-hidden="true" />
            Sistema: sem verificação
          </span>
        </div>
      </div>

      <div>
        <p className="text-xs uppercase tracking-wide text-fg-muted">Painel de snapshot (market-detail-view.tsx)</p>
        <div className="mt-2 rounded-md border border-border bg-bg-elevated p-3">
          <h3 className="text-xs font-medium uppercase tracking-wide text-fg-muted">
            Book<span className="ml-2 text-[11px] normal-case text-fg-subtle">Snapshot · há 2 min</span>
          </h3>
          <p className="mt-1 text-xs text-fg-muted">
            Não é uma fita ao vivo -- o tempo real só atualiza preço/bid/ask; book e trades ficam como estavam no
            carregamento da página até a próxima atualização.
          </p>
        </div>
      </div>
    </div>
  );
}
