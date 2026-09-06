import { Badge } from "@/components/ui/badge";
import { reasonLabel } from "@/components/lab/lab-format";
import type { OutcomeResult, ShadowTrackingState } from "@/lib/api/lab-types";

/**
 * `tracking_state`/`result` chips (brief S3b: "paleta semântica separada do
 * dourado"). Neutral/informational states use the same gray/info/warning
 * vocabulary `docs/DESIGN.md` §3 defines for status badges elsewhere;
 * green/red are reserved for a REAL financial result (`target`/`stop`),
 * never for a tracking-state fact like "no entry" or "censored", which are
 * not wins or losses.
 */
const TRACKING_LABEL: Record<ShadowTrackingState, string> = {
  pending_entry: "pendente de entrada",
  active: "ativo",
  terminal: "encerrado",
  no_entry: "sem entrada",
  censored: "censurado",
};

export function TrackingStateChip({ state, reason }: { state: ShadowTrackingState; reason: string | null }) {
  const suffix = reason ? `: ${reasonLabel(reason)}` : "";
  if (state === "active") return <Badge variant="info">{TRACKING_LABEL[state]}</Badge>;
  if (state === "no_entry") return <Badge variant="default">{`${TRACKING_LABEL[state]}${suffix}`}</Badge>;
  if (state === "censored") return <Badge variant="warning">{`${TRACKING_LABEL[state]}${suffix}`}</Badge>;
  return <Badge variant="outline">{TRACKING_LABEL[state]}</Badge>;
}

const RESULT_LABEL: Record<OutcomeResult, string> = {
  target: "alvo",
  stop: "stop",
  expired: "expirado",
  invalidated: "invalidado",
  open: "aberto",
};

export function ResultChip({ result }: { result: OutcomeResult }) {
  if (result === "target") return <Badge variant="positive">{RESULT_LABEL[result]}</Badge>;
  if (result === "stop") return <Badge variant="negative">{RESULT_LABEL[result]}</Badge>;
  if (result === "open") return <Badge variant="info">{RESULT_LABEL[result]}</Badge>;
  return <Badge variant="default">{RESULT_LABEL[result]}</Badge>;
}
