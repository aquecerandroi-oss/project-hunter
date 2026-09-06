import { Badge } from "@/components/ui/badge";
import type { AnomalyEvaluationStateValue } from "@/lib/api/anomalies-types";

/**
 * `AnomalyEvaluationState` (`hunter_core.domain.enums`): a second axis from
 * `AnomalyStatus`, never collapsed into it. `unknown` must never read as
 * "resolved" -- an anomaly whose feed disappeared stays `active` and
 * ineligible forever, which is exactly the case this chip exists to make
 * visible (`schemas/anomalies.py` module docstring).
 */
const VARIANT: Record<AnomalyEvaluationStateValue, "positive" | "warning" | "negative"> = {
  ok: "positive",
  stale: "warning",
  unknown: "negative",
};

const LABEL: Record<AnomalyEvaluationStateValue, string> = {
  ok: "avaliação ok",
  stale: "avaliação atrasada",
  unknown: "avaliação desconhecida",
};

export function EvaluationStateChip({ state }: { state: AnomalyEvaluationStateValue }) {
  return <Badge variant={VARIANT[state]}>{LABEL[state]}</Badge>;
}
