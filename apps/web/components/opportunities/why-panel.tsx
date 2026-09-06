import { isRecord, parseDecomposition, parseExplanation, parseFeatureSnapshot } from "@/components/opportunities/decomposition-parse";
import { WhyComponents } from "@/components/opportunities/why-components";
import { WhyContext } from "@/components/opportunities/why-context";
import { WhyFeatures } from "@/components/opportunities/why-features";
import { WhyFooter } from "@/components/opportunities/why-footer";
import { WhyHistory } from "@/components/opportunities/why-history";
import { WhySummary } from "@/components/opportunities/why-summary";
import type { OpportunityDetailOut } from "@/lib/api/opportunities-types";
import type { RegimeOut } from "@/lib/api/regime-types";

export interface WhyPanelProps {
  detail: OpportunityDetailOut;
  currentRegime: RegimeOut | null;
  orgId: string | undefined;
}

/**
 * "Por que estamos olhando isso?" (brief line 10, docs/PIPELINE.md §5-6):
 * summary -> component contributions -> anomalies/regime context -> feature
 * snapshot -> score history -> collapsed technical footer. Section order
 * mirrors how a trader would ask the question: what does the score say,
 * what built it, what is happening on the market right now, what raw data
 * fed it, how did it get here, and (only if pressed) the exact
 * baselines/versions behind it.
 */
export function WhyPanel({ detail, currentRegime, orgId }: WhyPanelProps) {
  const decomposition = parseDecomposition(isRecord(detail.decomposition) ? detail.decomposition : {});
  const explanation = parseExplanation(isRecord(detail.explanation) ? detail.explanation : {});
  const featureSnapshot = parseFeatureSnapshot(isRecord(detail.feature_snapshot) ? detail.feature_snapshot : {});

  return (
    <div className="flex flex-col gap-4">
      <WhySummary detail={detail} decomposition={decomposition} explanation={explanation} />
      <WhyComponents decomposition={decomposition} />
      <WhyContext detail={detail} currentRegime={currentRegime} />
      <WhyFeatures detail={detail} result={featureSnapshot} />
      <WhyHistory opportunityId={detail.id} orgId={orgId} history={detail.history} />
      <WhyFooter detail={detail} decomposition={decomposition} explanation={explanation} featureSnapshot={featureSnapshot} />
    </div>
  );
}
