import { Badge } from "@/components/ui/badge";
import type { badgeVariants } from "@/components/ui/badge";
import type { VariantProps } from "class-variance-authority";
import type { MarketRegimeValue, OpportunityStage, OpportunityStatus } from "@/lib/api/radar-types";

type BadgeVariant = VariantProps<typeof badgeVariants>["variant"];

/**
 * `OpportunityStatus` -> badge variant (docs/DESIGN.md §3's palette, extended
 * for the two members added by the T2 joint decision). `EXTENDED` and
 * `ANOMALY` share the `warning` variant (only 8 variants exist in
 * `components/ui/badge.tsx`, which this brief may not touch) -- the label
 * text is what tells them apart, never the color alone. `EXPIRED` is
 * `outline`: a terminal, inactive episode should read as quieter than every
 * live status, not confused with `NORMAL`'s neutral-but-active default.
 */
const STATUS_VARIANT: Record<OpportunityStatus, BadgeVariant> = {
  NORMAL: "default",
  WATCHING: "info",
  ANOMALY: "warning",
  HOT: "gold",
  ENTRY_CANDIDATE: "positive",
  EXTENDED: "warning",
  EXPIRED: "outline",
};

export function StatusChip({ status }: { status: OpportunityStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>;
}

const STAGE_VARIANT: Record<Exclude<OpportunityStage, "NONE">, BadgeVariant> = {
  EARLY: "info",
  DEVELOPING: "default",
  EXTENDED: "warning",
};

/** `OpportunityStage.NONE` is a real member ("we cannot tell yet"), not a null -- rendered as muted text, never hidden or mistaken for `EARLY`. */
export function StageChip({ stage }: { stage: OpportunityStage }) {
  if (stage === "NONE") return <span className="text-xs text-fg-subtle">estágio indisponível</span>;
  return <Badge variant={STAGE_VARIANT[stage]}>{stage}</Badge>;
}

/** `regime` is `null` on a radar/opportunity row when the episode has no linked regime -- distinct from `MarketRegime.UNKNOWN`, a real classification. */
export function RegimeChip({ regime }: { regime: MarketRegimeValue | null | undefined }) {
  if (!regime) return <span className="text-xs text-fg-subtle">sem regime</span>;
  return <Badge variant="outline">{regime}</Badge>;
}

export function InPositionChip({ inPosition }: { inPosition: boolean | null | undefined }) {
  if (inPosition !== true) return null;
  return <Badge variant="positive">Em posição</Badge>;
}

export function RiskBlockedChip({ riskBlocked, reason }: { riskBlocked: boolean | null | undefined; reason?: string | null }) {
  if (riskBlocked !== true) return null;
  return (
    <Badge variant="negative" title={reason ?? undefined}>
      Bloqueado (risco)
    </Badge>
  );
}
