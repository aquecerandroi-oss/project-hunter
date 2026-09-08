import { Badge } from "@/components/ui/badge";
import { reasonLabel } from "@/components/lab/lab-format";
import { resultLabel, trackingLabel } from "@/components/lab/labels";
import type { OutcomeResult, ShadowTrackingState } from "@/lib/api/lab-types";

/**
 * `tracking_state`/`result` chips (brief S3b: "paleta semântica separada do
 * dourado"). Neutral/informational states use the same gray/info/warning
 * vocabulary `docs/DESIGN.md` §3 defines for status badges elsewhere;
 * green/red are reserved for a REAL financial result (`target`/`stop`),
 * never for a tracking-state fact like "no entry" or "censored", which are
 * not wins or losses. Labels themselves now live in `components/lab/labels.ts`
 * (brief T3.24b: one dictionary per domain).
 */
export function TrackingStateChip({ state, reason }: { state: ShadowTrackingState; reason: string | null }) {
  const label = trackingLabel(state);
  const suffix = reason ? `: ${reasonLabel(reason)}` : "";
  if (state === "active") return <Badge variant="info">{label}</Badge>;
  if (state === "no_entry") return <Badge variant="default">{`${label}${suffix}`}</Badge>;
  if (state === "censored") return <Badge variant="warning">{`${label}${suffix}`}</Badge>;
  return <Badge variant="outline">{label}</Badge>;
}

export function ResultChip({ result }: { result: OutcomeResult }) {
  const label = resultLabel(result);
  if (result === "target") return <Badge variant="positive">{label}</Badge>;
  if (result === "stop") return <Badge variant="negative">{label}</Badge>;
  if (result === "open") return <Badge variant="info">{label}</Badge>;
  return <Badge variant="default">{label}</Badge>;
}
