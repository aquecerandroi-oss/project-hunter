import { ArrowDownRight, ArrowUpRight } from "lucide-react";

/**
 * Illustrates the KPI card anchor (docs/DESIGN.md §3): 12px uppercase
 * `fg-muted` title, 28px tabular value, semantic variation with an arrow,
 * `border` that elevates to `border-strong` on hover. The values below are
 * static preview labels ("exemplo"), not real data -- this page is dev-only
 * (see app/_design/page.tsx) and never reachable in production, so it does
 * not fall under CLAUDE.md's "no invented numbers in production" rule.
 */
export function KpiCardShowcase() {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <section className="rounded-lg border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong">
        <h3 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Exemplo -- PnL (24h)</h3>
        <p className="num mt-1 text-[28px] font-semibold text-fg">$12.480,50</p>
        <p className="num mt-1 flex items-center gap-1 text-sm text-green">
          <ArrowUpRight className="size-4" aria-hidden="true" />
          +1,23%
        </p>
      </section>
      <section className="rounded-lg border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong">
        <h3 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Exemplo -- Exposição</h3>
        <p className="num mt-1 text-[28px] font-semibold text-fg">$3.900,00</p>
        <p className="num mt-1 flex items-center gap-1 text-sm text-red">
          <ArrowDownRight className="size-4" aria-hidden="true" />
          -0,45%
        </p>
      </section>
    </div>
  );
}
