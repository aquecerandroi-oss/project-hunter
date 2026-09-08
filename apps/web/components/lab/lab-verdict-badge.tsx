import { Badge } from "@/components/ui/badge";
import { verdictBadgeVariant, verdictLabel, VERDICT_RULE_TEXT } from "@/components/lab/lab-scoreboard";

/**
 * The Placar's dominant element (brief T3.18 item 3): "inconclusiva" muted
 * (`outline`), "validada" positive (green), "reprovada" negative (red) --
 * the rule that produced it is always one hover away (brief item 5: "sempre
 * ao lado da régua"), never a bare label that could read as a promise.
 */
export function LabVerdictBadge({ verdict }: { verdict: string }) {
  return (
    <Badge
      variant={verdictBadgeVariant(verdict)}
      title={VERDICT_RULE_TEXT}
      className="w-fit text-sm font-semibold underline decoration-dotted underline-offset-2"
    >
      {verdictLabel(verdict)}
    </Badge>
  );
}
