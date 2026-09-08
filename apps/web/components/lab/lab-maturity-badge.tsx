import { Badge } from "@/components/ui/badge";
import type { MaturityOut } from "@/lib/api/lab-types";

export interface LabMaturityBadgeProps {
  maturity: MaturityOut;
  /** One-line, no subtitle -- the `<summary>` of `LabVersionCard`'s `<details>` (brief T3.24b item [4]: "Inconclusivo · 37/100 · 2/30 dias"). */
  compact?: boolean;
}

const NOTE = "— ainda pesquisa, nunca promessa";

/**
 * SHADOW-LAB.md §9's editorial threshold: before 100 evaluable outcomes AND
 * 30 distinct days, the version is "inconclusivo" -- a neutral, expected
 * state of the experiment, never an error or a warning color. Above the
 * threshold the label becomes "Pesquisa", never a promise -- this API does
 * not compute the resampling/sensitivity analysis §9 also calls for, so this
 * badge never implies more certainty than the two counts it actually has.
 * One shared note for both states (brief T3.24b item [4]): "— ainda
 * pesquisa, nunca promessa".
 */
export function LabMaturityBadge({ maturity, compact = false }: LabMaturityBadgeProps) {
  const label = maturity.inconclusive ? "Inconclusivo" : "Pesquisa";

  if (compact) {
    return (
      <Badge variant="outline" className="w-fit font-mono tabular-nums">
        {`${label} · ${maturity.evaluable_outcomes}/100 · ${maturity.distinct_days}/30 dias`}
      </Badge>
    );
  }

  if (maturity.inconclusive) {
    return (
      <div className="flex flex-col gap-0.5">
        <Badge variant="outline" className="w-fit font-mono tabular-nums">
          {`Inconclusivo · ${maturity.evaluable_outcomes} resultados avaliáveis / 100 · ${maturity.distinct_days} dias distintos / 30`}
        </Badge>
        <span className="text-[11px] text-fg-subtle">{`nesta janela e coorte ${NOTE}`}</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      <Badge variant="outline" className="w-fit">
        Pesquisa
      </Badge>
      <span className="text-[11px] text-fg-subtle">
        {`${maturity.evaluable_outcomes} resultados avaliáveis, ${maturity.distinct_days} dias distintos ${NOTE}`}
      </span>
    </div>
  );
}
