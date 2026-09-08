import type { ReactNode } from "react";

import { LabScoreboardCard } from "@/components/lab/lab-scoreboard-card";
import { LabSegmentTabs } from "@/components/lab/lab-segment-tabs";
import { LabSignalRow } from "@/components/lab/lab-signal-row";
import { labSignalsHeaders, LabSignalsTableHead } from "@/components/lab/lab-signals-table-head";
import { exampleRuler, exampleScoreboardRow, exampleSignal } from "@/tests/fixtures/lab";

/**
 * Brief T3.24b §3: options A ("Placar-primeiro") and B ("Sinais-primeiro")
 * from `.claude/state/review-design-2026-09-08.md`'s hierarchy report,
 * rendered with the *real* components (`LabScoreboardCard`, `LabSegmentTabs`,
 * `LabSignalRow`) and the same fixtures `lab-*.test.tsx` use -- so the
 * comparison is never a drawing, always the actual pixels the real data
 * produces. Everton's decision (D18, 2026-09-08) already picked option A for
 * `/lab` itself; this mockup stays for the product-designer's record and is
 * dev-only (`app/_design` 404s in production).
 */
const FIXTURE_LABEL = "fixture de teste, dado de 2026-09-06/08 (tests/fixtures/lab.ts)";

function ScoreboardPreview() {
  return <LabScoreboardCard row={exampleScoreboardRow()} ruler={exampleRuler()} />;
}

function SignalsPreview() {
  const row = exampleSignal();
  const headers = labSignalsHeaders(false);
  return (
    <div className="flex flex-col gap-2">
      <LabSegmentTabs rows={[row]} value="concluded" onChange={() => {}} />
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-left text-[13px]">
          <LabSignalsTableHead showResearch={false} panelOpen={false} />
          <tbody>
            <LabSignalRow
              id="showcase-row"
              orgSlug="preview"
              row={row}
              versionLabel="momentum/v2"
              ruler={exampleRuler()}
              showResearch={false}
              rowHeight={40}
              selected={false}
              ariaRowIndex={2}
              panelOpen={false}
              onOpen={() => {}}
            />
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-fg-subtle">{headers.length} colunas na visão padrão.</p>
    </div>
  );
}

function OptionColumn({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return (
    <div className="flex flex-1 flex-col gap-3 rounded-lg border border-border bg-bg-elevated p-4">
      <div>
        <p className="text-sm font-semibold text-fg">{title}</p>
        <p className="text-xs text-fg-muted">{note}</p>
      </div>
      {children}
    </div>
  );
}

/** Side-by-side comparison for the product-designer/Everton (brief §3). */
export function LabHierarchyShowcase() {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] text-fg-subtle">{FIXTURE_LABEL}</p>
      <div className="flex flex-col gap-4 lg:flex-row">
        <OptionColumn title="Opção A -- Placar-primeiro (D18, escolhida)" note="Faixa SOMBRA -> Placar -> Sinais -> Versões">
          <p className="text-xs font-medium uppercase tracking-wide text-fg-muted">1. Placar</p>
          <ScoreboardPreview />
          <p className="text-xs font-medium uppercase tracking-wide text-fg-muted">2. Sinais — Sombra</p>
          <SignalsPreview />
        </OptionColumn>
        <OptionColumn title="Opção B -- Sinais-primeiro (não escolhida)" note="Faixa SOMBRA -> Sinais -> Placar -> Versões">
          <p className="text-xs font-medium uppercase tracking-wide text-fg-muted">1. Sinais — Sombra</p>
          <SignalsPreview />
          <p className="text-xs font-medium uppercase tracking-wide text-fg-muted">2. Placar</p>
          <ScoreboardPreview />
        </OptionColumn>
      </div>
    </div>
  );
}
