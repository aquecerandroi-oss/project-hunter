/** Honest empty universe (docs/plans/M1.md T1.5): the API answered, there is just nothing monitored yet. */
export function MarketsEmpty() {
  return (
    <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">
        Nenhum mercado monitorado ainda — o market-worker precisa estar rodando (System → Workers).
      </p>
    </div>
  );
}
