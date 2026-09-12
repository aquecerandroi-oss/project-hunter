/**
 * `meme_features_1m` series (detail page): one row per closed minute. Every
 * dependent metric (`curve_progress_pct`, `mcap_sol`, `unique_buyers`,
 * `buy_sell_ratio`, `top10_share`, `creator_sold`) renders its value OR
 * "sem medição: <motivo>" (`memeNullReasonText`) -- never a blank cell, never
 * a `0`/`false` standing in for "not measured" (docs/DESIGN.md, T4.3
 * acceptance criteria). `coverage` (fraction of the minute actually
 * observed) is never null, so it always renders a real percentage.
 *
 * T4.10b: the trend-line columns (support + distance, higher lows, breakout)
 * and `hype_score` of `meme_features_v3` (`meme-features-line-cells.tsx`),
 * read tolerantly -- a row from an older version says "linha: sem leitura".
 */
import { BrasiliaShort } from "@/components/time/brasilia-instant";
import type { MemeFeaturePoint, MemeNullReason } from "@/lib/api/meme-types";

import { memeNullReasonText } from "./labels";
import { HypeCell, LineCells } from "./meme-features-line-cells";
import { formatMemePct, formatRatio, formatSol } from "./meme-format";

function Reasoned({
  value,
  reason,
  format,
}: {
  value: string | null;
  reason: MemeNullReason | null | undefined;
  format: (v: string) => string;
}) {
  if (value === null) return <span className="text-fg-subtle">{memeNullReasonText(reason)}</span>;
  return <span className="tabular-nums">{format(value)}</span>;
}

export interface MemeFeaturesTableProps {
  features: MemeFeaturePoint[];
}

export function MemeFeaturesTable({ features }: MemeFeaturesTableProps) {
  if (features.length === 0) {
    return <p className="text-sm text-fg-muted">Nenhum minuto computado ainda para este token.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-left text-[13px]">
        <thead className="bg-bg-elevated text-[11px] uppercase tracking-wide text-fg-muted">
          <tr>
            <th className="px-3 py-2">Minuto</th>
            <th className="px-3 py-2 text-right">Progresso</th>
            <th className="px-3 py-2 text-right">Mcap (SOL)</th>
            <th className="hidden px-3 py-2 text-right md:table-cell">Compradores únicos</th>
            <th className="hidden px-3 py-2 text-right md:table-cell">Compra/venda</th>
            <th className="hidden px-3 py-2 text-right md:table-cell">Top 10 holders</th>
            <th className="hidden px-3 py-2 text-right md:table-cell">Dev vendeu</th>
            <th className="hidden px-3 py-2 text-right md:table-cell">Suporte (SOL)</th>
            <th className="hidden px-3 py-2 text-right md:table-cell">Fundos ascendentes</th>
            <th className="hidden px-3 py-2 text-right md:table-cell">Rompimento 15 min</th>
            <th className="px-3 py-2 text-right">Hype</th>
            <th className="px-3 py-2 text-right">Cobertura</th>
          </tr>
        </thead>
        <tbody>
          {features.map((row) => (
            <tr key={row.end_time} className="border-t border-border odd:bg-bg-overlay/40">
              <td className="whitespace-nowrap px-3 py-2">
                <BrasiliaShort iso={row.end_time} />
              </td>
              <td className="px-3 py-2 text-right">
                <Reasoned value={row.curve_progress_pct} reason={row.progress_reason} format={formatMemePct} />
              </td>
              <td className="px-3 py-2 text-right">
                <Reasoned value={row.mcap_sol} reason={row.curve_reason} format={formatSol} />
              </td>
              <td className="hidden px-3 py-2 text-right md:table-cell">
                {row.unique_buyers === null ? (
                  <span className="text-fg-subtle">{memeNullReasonText(row.unique_buyers_reason)}</span>
                ) : (
                  <span className="tabular-nums">{row.unique_buyers}</span>
                )}
              </td>
              <td className="hidden px-3 py-2 text-right md:table-cell">
                <Reasoned value={row.buy_sell_ratio} reason={row.buy_sell_ratio_reason} format={formatRatio} />
              </td>
              <td className="hidden px-3 py-2 text-right md:table-cell">
                <Reasoned value={row.top10_share} reason={row.top10_share_reason} format={formatMemePct} />
              </td>
              <td className="hidden px-3 py-2 text-right md:table-cell">
                {row.creator_sold === null ? (
                  <span className="text-fg-subtle">{memeNullReasonText(row.creator_sold_reason)}</span>
                ) : (
                  <span>{row.creator_sold ? "Sim" : "Não"}</span>
                )}
              </td>
              <LineCells row={row} />
              <HypeCell row={row} />
              <td className="px-3 py-2 text-right tabular-nums">{formatMemePct(row.coverage, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
