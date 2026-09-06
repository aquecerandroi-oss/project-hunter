import type { DecompositionResult, ParsedComponent } from "@/components/opportunities/decomposition-parse";

function toNumber(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const KIND_LABEL: Record<string, string> = {
  mad: "Momentum/Volume/Liquidez/Fluxo/Derivativos",
  regime: "Regime de mercado",
  anomalies: "Anomalias",
  consensus: "Consenso de agentes",
  external: "Inteligência externa",
};

function ComponentBar({ component }: { component: ParsedComponent }) {
  const normalized = toNumber(component.normalized);
  return (
    <div className="flex flex-col gap-1 border-b border-border/60 py-2 last:border-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-fg">{component.name}</span>
        <span className="text-xs text-fg-muted">peso {component.weight}</span>
      </div>
      {component.available && normalized !== null ? (
        <>
          <div className="h-2 w-full overflow-hidden rounded-full bg-bg-overlay" role="img" aria-label={`${component.name}: ${component.normalized} de 100`}>
            <div className="h-full bg-fg-muted" style={{ width: `${Math.max(0, Math.min(100, normalized))}%` }} />
          </div>
          <span className="font-mono text-xs tabular-nums text-fg-muted">
            normalizado {component.normalized} · contribuiu {component.contribution} pontos
            {component.expected > 0 ? ` · ${component.used}/${component.expected} entradas` : ""}
          </span>
        </>
      ) : (
        // Never a bar at 0% pretending an unavailable component was observed
        // as zero (Astra's T2.7 review, must-fix 4) -- a dashed placeholder
        // plus the real reason instead.
        <div className="flex items-center gap-2">
          <div className="h-2 w-full rounded-full border border-dashed border-border" aria-hidden="true" />
          <span className="whitespace-nowrap text-xs text-fg-muted">sem dado{component.reason ? ` (${component.reason})` : ""}</span>
        </div>
      )}
    </div>
  );
}

/**
 * The component breakdown (brief line 10: "componentes, pesos, contribuições
 * (barras horizontais calmas)"). Renders every component the scorer produced
 * (`PIPELINE.md` §5's full table: Momentum..External Intelligence), not only
 * the MAD ones -- Regime/Anomalies/Consensus/External go through the same
 * `assemble_component` (`opportunity/components.py:140`) and carry the same
 * weight/normalized/contribution/available/reason fields. Early-Movement is
 * shown separately, never folded into this weighted list: it is a signed
 * term OUTSIDE the weight budget (Astra's T2.7 review, must-fix 4).
 */
export function WhyComponents({ decomposition }: { decomposition: DecompositionResult }) {
  if (!decomposition.recognized) {
    return (
      <section className="rounded-lg border border-border bg-bg-elevated p-4">
        <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Componentes</h2>
        <p className="mt-2 text-sm text-fg-muted">Decomposição em formato não reconhecido -- ver JSON bruto no rodapé técnico.</p>
      </section>
    );
  }

  const sorted = [...decomposition.components].sort((a, b) => (toNumber(b.contribution) ?? 0) - (toNumber(a.contribution) ?? 0));
  const em = decomposition.earlyMovement;
  const emContribution = toNumber(em.contribution) ?? 0;

  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4">
      <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Componentes</h2>
      <div className="mt-2">
        {sorted.map((component) => (
          <div key={component.name} title={KIND_LABEL[component.kind]}>
            <ComponentBar component={component} />
          </div>
        ))}
      </div>
      {em.e !== 0 && (
        <p className="mt-3 border-t border-border pt-2 text-xs text-fg-muted">
          Early-Movement (estágio {em.stage}, direção {em.stageDirection}, fora do orçamento de pesos):{" "}
          <span className={emContribution >= 0 ? "text-green" : "text-red"}>
            {emContribution >= 0 ? "+" : ""}
            {em.contribution}
          </span>{" "}
          pontos.
        </p>
      )}
    </section>
  );
}
