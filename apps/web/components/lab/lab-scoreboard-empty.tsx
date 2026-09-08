/**
 * Whole-Placar empty state (brief T3.18 item 3: "no signals yet"). The
 * scoreboard API only ever returns a row for a version that has emitted at
 * least one signal (`notes-T3.18.md`), so an empty `rows` array here means
 * literally no `strategy_version` has emitted anything yet -- an honest,
 * operational absence (docs/DESIGN.md §2), never "not built yet".
 */
export function LabScoreboardEmpty() {
  return (
    <div className="rounded-lg border border-dashed border-border p-6 text-center">
      <p className="text-sm text-fg">Nenhuma versão do Lab emitiu sinal ainda.</p>
      <p className="mt-1 text-xs text-fg-muted">
        O placar aparece assim que a primeira versão de estratégia emitir um sinal (cohort &quot;prospective&quot;).
      </p>
    </div>
  );
}
