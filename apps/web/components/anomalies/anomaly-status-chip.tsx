import { Badge } from "@/components/ui/badge";
import type { AnomalyStatusValue } from "@/lib/api/anomalies-types";

const VARIANT: Record<AnomalyStatusValue, "warning" | "default" | "outline"> = {
  active: "warning",
  resolved: "default",
  expired: "outline",
};

const LABEL: Record<AnomalyStatusValue, string> = {
  active: "ativa",
  resolved: "resolvida",
  expired: "expirada",
};

/** `AnomalyStatus` (`active`/`resolved`/`expired`) -- the lifecycle axis, distinct from `EvaluationStateChip`'s data-trust axis. */
export function AnomalyStatusChip({ status }: { status: AnomalyStatusValue }) {
  return <Badge variant={VARIANT[status]}>{LABEL[status]}</Badge>;
}
