import { LabScoreboardCard } from "@/components/lab/lab-scoreboard-card";
import { LabScoreboardEmpty } from "@/components/lab/lab-scoreboard-empty";
import { sortScoreboardRows } from "@/components/lab/lab-scoreboard";
import type { MoneyRuler } from "@/components/lab/lab-money";
import type { ScoreboardRowOut } from "@/lib/api/lab-types";

export interface LabScoreboardSectionProps {
  rows: ScoreboardRowOut[];
  ruler: MoneyRuler;
}

/**
 * The Placar (brief T3.18 item 3): one card per `strategy_version` that has
 * ever emitted a signal, active-first then by `sum_r`. A pure server
 * component -- ordering needs no client state, only `LabScoreboardCard`'s
 * own "Detalhes de pesquisa" toggle does.
 */
export function LabScoreboardSection({ rows, ruler }: LabScoreboardSectionProps) {
  if (rows.length === 0) return <LabScoreboardEmpty />;
  const sorted = sortScoreboardRows(rows);
  return (
    <div data-testid="lab-scoreboard-section" className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {sorted.map((row) => (
        <LabScoreboardCard key={row.version.id} row={row} ruler={ruler} />
      ))}
    </div>
  );
}
