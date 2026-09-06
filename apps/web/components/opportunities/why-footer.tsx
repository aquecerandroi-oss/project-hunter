import type { DecompositionResult, ExplanationResult, FeatureSnapshotResult } from "@/components/opportunities/decomposition-parse";
import type { OpportunityDetailOut } from "@/lib/api/opportunities-types";

export interface WhyFooterProps {
  detail: OpportunityDetailOut;
  decomposition: DecompositionResult;
  explanation: ExplanationResult;
  featureSnapshot: FeatureSnapshotResult;
}

/**
 * The technical footer (brief line 10: "baseline_ids/versões num rodapé
 * técnico colapsado"). Collapsed by default -- `<details>`, no JS needed to
 * open it. Also where every "ver JSON bruto no rodapé técnico" pointer
 * elsewhere in the panel actually resolves (Astra's T2.7 diff review,
 * must-fix 6: the promise used to point at a footer that only ever showed
 * ids/versions, never the raw payload of an unrecognized shape).
 */
export function WhyFooter({ detail, decomposition, explanation, featureSnapshot }: WhyFooterProps) {
  const baselineIds = decomposition.recognized ? decomposition.baselineIds : detail.baseline_ids;
  return (
    <details className="rounded-lg border border-border bg-bg-elevated p-4">
      <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-fg-muted">Rodapé técnico</summary>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-fg-muted">weights_version</dt>
          <dd className="font-mono text-fg">{detail.weights_version ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-fg-muted">regime_id</dt>
          <dd className="font-mono text-fg">{detail.regime_id ?? "—"}</dd>
        </div>
        {decomposition.recognized && (
          <div>
            <dt className="text-fg-muted">scorer_version</dt>
            <dd className="font-mono text-fg">{decomposition.scorerVersion ?? "—"}</dd>
          </div>
        )}
        <div className="sm:col-span-2">
          <dt className="text-fg-muted">baseline_ids ({baselineIds.length})</dt>
          <dd className="break-all font-mono text-fg">{baselineIds.length > 0 ? baselineIds.join(", ") : "—"}</dd>
        </div>
      </dl>
      {!decomposition.recognized && (
        <RawJsonBlock label="decomposition (formato não reconhecido)" value={decomposition.raw} />
      )}
      {!explanation.recognized && <RawJsonBlock label="explanation (formato não reconhecido)" value={explanation.raw} />}
      {!featureSnapshot.recognized && <RawJsonBlock label="feature_snapshot (formato não reconhecido)" value={featureSnapshot.raw} />}
    </details>
  );
}

function RawJsonBlock({ label, value }: { label: string; value: Record<string, unknown> }) {
  return (
    <div className="mt-3">
      <p className="text-xs text-fg-muted">{label}</p>
      <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-bg-overlay p-2 text-[10px] text-fg-subtle">{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}
