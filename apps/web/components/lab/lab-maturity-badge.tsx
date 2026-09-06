import { Badge } from "@/components/ui/badge";
import type { MaturityOut } from "@/lib/api/lab-types";

export interface LabMaturityBadgeProps {
  maturity: MaturityOut;
}

/**
 * SHADOW-LAB.md §9's editorial threshold: before 100 evaluable outcomes AND
 * 30 distinct days, the version is "inconclusivo" -- a neutral, expected
 * state of the experiment, never an error or a warning color. Above the
 * threshold the label becomes "Pesquisa", never a promise (§9: "e ainda
 * assim 'pesquisa', nunca promessa") -- this API does not compute the
 * resampling/sensitivity analysis §9 also calls for, so this badge never
 * implies more certainty than the two counts it actually has.
 */
export function LabMaturityBadge({ maturity }: LabMaturityBadgeProps) {
  if (maturity.inconclusive) {
    return (
      <div className="flex flex-col gap-0.5">
        <Badge variant="outline" className="w-fit font-mono tabular-nums">
          {`Inconclusivo · ${maturity.evaluable_outcomes} outcomes avaliáveis / 100 · ${maturity.distinct_days} dias distintos / 30`}
        </Badge>
        <span className="text-[11px] text-fg-subtle">nesta janela e coorte -- não é erro, é a regra editorial</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      <Badge variant="outline" className="w-fit">
        Pesquisa
      </Badge>
      <span className="text-[11px] text-fg-subtle">
        {`${maturity.evaluable_outcomes} outcomes avaliáveis, ${maturity.distinct_days} dias distintos -- ainda pesquisa, nunca promessa`}
      </span>
    </div>
  );
}
