import type { FeatureSnapshotResult } from "@/components/opportunities/decomposition-parse";
import type { OpportunityDetailOut } from "@/lib/api/opportunities-types";

const QUALITY_LABEL: Record<string, string> = { ok: "ok", degraded: "degradado", unavailable: "indisponível" };

/**
 * The `feature_snapshot` compact table (brief line 10: "features do
 * feature_snapshot, tabela compacta com quality/motivo"). `result` is parsed
 * once by `why-panel.tsx` (`decomposition-parse.ts::parseFeatureSnapshot`)
 * and shared with `why-footer.tsx`'s raw-JSON fallback, rather than
 * re-parsed here.
 */
export function WhyFeatures({ detail, result }: { detail: OpportunityDetailOut; result: FeatureSnapshotResult }) {
  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4">
      <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Features</h2>
      {!result.recognized ? (
        <p className="mt-2 text-sm text-fg-muted">
          {Object.keys(detail.feature_snapshot).length === 0
            ? "Sem feature_snapshot ainda para este episódio."
            : "feature_snapshot em formato não reconhecido -- ver JSON bruto no rodapé técnico."}
        </p>
      ) : result.features.length === 0 ? (
        <p className="mt-2 text-sm text-fg-muted">Nenhuma feature no vetor deste episódio.</p>
      ) : (
        <table className="mt-2 w-full text-left text-xs">
          <thead className="text-fg-muted">
            <tr>
              <th className="py-1 pr-3 font-medium">Feature</th>
              <th className="py-1 pr-3 text-right font-medium">Valor</th>
              <th className="py-1 pr-3 font-medium">Qualidade</th>
              <th className="py-1 font-medium">Motivo</th>
            </tr>
          </thead>
          <tbody>
            {result.features.map((f) => (
              <tr key={f.key} className="border-t border-border/60">
                <td className="py-1 pr-3 font-mono text-fg">{f.key}</td>
                <td className="py-1 pr-3 text-right font-mono tabular-nums text-fg">{f.value ?? "—"}</td>
                <td className="py-1 pr-3 text-fg-muted">{QUALITY_LABEL[f.quality] ?? f.quality}</td>
                <td className="py-1 text-fg-muted">{f.reason ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
