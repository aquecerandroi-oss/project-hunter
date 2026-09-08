import { LabCurveChart } from "@/components/lab/lab-curve-chart";
import { buildCurveSeries, sortScoreboardRows } from "@/components/lab/lab-scoreboard";
import type { MoneyRuler } from "@/components/lab/lab-money";
import type { CurveOut, ScoreboardRowOut } from "@/lib/api/lab-types";

export interface LabCurveSectionProps {
  rows: ScoreboardRowOut[];
  curvesById: Record<string, CurveOut | null>;
  ruler: MoneyRuler;
}

/** The Placar's curve (brief T3.18 item 4) -- same order as the cards above (active first, then `sum_r`). */
export function LabCurveSection({ rows, curvesById, ruler }: LabCurveSectionProps) {
  if (rows.length === 0) {
    return <p className="text-sm text-fg-muted">Nenhuma curva disponível: nenhuma versão emitiu sinal ainda.</p>;
  }
  const series = buildCurveSeries(sortScoreboardRows(rows), curvesById);
  return <LabCurveChart series={series} ruler={ruler} />;
}
