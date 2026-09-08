"use client";

import { useState } from "react";

import { Select } from "@/components/ui/select";
import { LabCurveChart } from "@/components/lab/lab-curve-chart";
import { buildCurveSeries, sortScoreboardRows } from "@/components/lab/lab-scoreboard";
import type { MoneyRuler } from "@/components/lab/lab-money";
import { loadLabCurveAction } from "@/lib/api/lab-actions";
import type { CurveOut, ScoreboardRowOut } from "@/lib/api/lab-types";
import { logger } from "@/lib/logger";

export interface LabCurveSectionProps {
  rows: ScoreboardRowOut[];
  curvesById: Record<string, CurveOut | null>;
  ruler: MoneyRuler;
  /** The Placar's own frozen `as_of` (`lab/page.tsx`'s `loadScoreboard`) -- every on-demand replay curve fetch below reuses it, so it never disagrees with the prospective population already on screen. */
  asOf: string;
}

type CurveCohort = "prospective" | "replay";

/**
 * The Placar's curve (brief T3.18 item 4), extended by T3.24b addendum A3
 * with a "Coorte da curva" selector: "prospectiva" (default, server-loaded)
 * or "replay" -- which fetches `GET /lab/shadow/curve?cohort=replay` for
 * every row on demand (via a Server Action, `components/**` never imports
 * `@/lib/server/**`) and draws it dashed, alongside the still-visible
 * prospective line. Same order as the cards above (active first, then
 * `sum_r`).
 */
export function LabCurveSection({ rows, curvesById, ruler, asOf }: LabCurveSectionProps) {
  const [cohort, setCohort] = useState<CurveCohort>("prospective");
  const [replayCurvesById, setReplayCurvesById] = useState<Record<string, CurveOut | null> | null>(null);
  const [loadingReplay, setLoadingReplay] = useState(false);

  if (rows.length === 0) {
    return <p className="text-sm text-fg-muted">Nenhuma curva disponível: nenhuma versão emitiu sinal ainda.</p>;
  }

  const sorted = sortScoreboardRows(rows);

  async function loadReplayCurves(): Promise<void> {
    setLoadingReplay(true);
    try {
      const entries = await Promise.all(
        sorted.map(async (row) => {
          const outcome = await loadLabCurveAction({ version_id: row.version.id, as_of: asOf, cohort: "replay" });
          return [row.version.id, outcome.ok ? outcome.curve : null] as const;
        }),
      );
      setReplayCurvesById(Object.fromEntries(entries));
    } catch (error) {
      logger.error("lab_curve_replay_load_failed", { error: String(error) });
      setReplayCurvesById({});
    } finally {
      setLoadingReplay(false);
    }
  }

  function handleCohortChange(next: CurveCohort): void {
    setCohort(next);
    if (next === "replay" && replayCurvesById === null) void loadReplayCurves();
  }

  const prospectiveSeries = buildCurveSeries(sorted, curvesById, "prospective");
  const replaySeries = cohort === "replay" && replayCurvesById ? buildCurveSeries(sorted, replayCurvesById, "replay") : [];
  const series = [...prospectiveSeries, ...replaySeries];

  return (
    <div className="flex flex-col gap-2">
      <label className="flex items-center gap-2 text-xs">
        <span className="text-fg-muted">Coorte da curva</span>
        <Select
          aria-label="Coorte da curva"
          value={cohort}
          onChange={(event) => handleCohortChange(event.target.value as CurveCohort)}
          className="h-7 text-[13px]"
        >
          <option value="prospective">prospectiva (padrão)</option>
          <option value="replay">replay</option>
        </Select>
        {loadingReplay && <span className="text-fg-subtle">carregando replay...</span>}
      </label>
      <LabCurveChart series={series} ruler={ruler} />
    </div>
  );
}
