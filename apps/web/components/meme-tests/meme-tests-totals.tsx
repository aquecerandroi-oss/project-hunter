import { formatR, formatSolSigned, signClass } from "@/components/meme-desk/meme-desk-format";
import type { MemeTestsSources, MemeTestsTotals } from "@/lib/api/meme-tests-types";

import { walletsSourceLabel } from "./labels";
import { formatUsdSigned } from "./meme-tests-format";

export interface MemeTestsTotalsProps {
  totals: MemeTestsTotals;
  sources: MemeTestsSources;
}

function Stat({ label, value, hint, valueClass = "text-fg" }: { label: string; value: string; hint?: string | undefined; valueClass?: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs uppercase tracking-wide text-fg-muted">{label}</p>
      <p className={`font-mono text-xl font-semibold tabular-nums ${valueClass}`}>{value}</p>
      {hint && <p className="text-[11px] text-fg-subtle">{hint}</p>}
    </div>
  );
}

/** The day's totals over every row of the filter (the API computes them in SQL, never over the loaded page). */
export function MemeTestsTotals({ totals, sources }: MemeTestsTotalsProps) {
  const hitRate = totals.closed > 0 ? `${totals.wins} de ${totals.closed}` : "sem fechadas";
  const usd = totals.pnl_usd === null ? "sem cotação" : formatUsdSigned(totals.pnl_usd);
  const usdHint = totals.unpriced_usd > 0 ? `${totals.unpriced_usd} fechada(s) sem cotação SOL/USD na saída` : "fechadas, à cotação observada na saída";
  return (
    <section aria-label="Totais do dia" className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      <Stat label="Apostas" value={String(totals.bets)} hint={`${totals.closed} fechada(s) · ${totals.open} aberta(s)`} />
      <Stat label="Acertos" value={hitRate} hint={totals.closed > 0 ? `${totals.losses} perda(s)` : undefined} />
      <Stat label="PnL SOL" value={formatSolSigned(totals.pnl_sol)} hint={`abertas à marca: ${formatSolSigned(totals.provisional_pnl_sol)}`} valueClass={signClass(totals.pnl_sol)} />
      <Stat label="PnL US$" value={usd} hint={usdHint} valueClass={totals.pnl_usd === null ? "text-fg-muted" : signClass(totals.pnl_usd)} />
      <Stat label="R somado" value={formatR(totals.r_sum)} hint="fechadas" valueClass={signClass(totals.r_sum)} />
      <Stat label="REAL" value={sources.wallets === "observada" ? String(totals.real_rows) : "—"} hint={walletsSourceLabel(sources.wallets)} valueClass={sources.wallets === "observada" ? "text-fg" : "text-fg-muted"} />
    </section>
  );
}
