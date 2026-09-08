/**
 * Ausência operacional (docs/DESIGN.md §2): the wallet feature exists and is
 * implemented, there is simply no principal paper wallet open for this
 * organization yet -- opening one is a once-per-organization operator act
 * (`infra/scripts/open_paper_wallet.py`'s own docstring: "opening one is a
 * once-per-organization act... never a route to a reset"), not something
 * this screen can offer a button for without fabricating a second write path
 * the API does not have. No button that pretends to open a wallet. The
 * runbook command is disclosed, but behind a `<details>` (DESIGN-5, "sem
 * backstage na copy": the ADR number and the command are not the screen's
 * main message for the product, even though the operator today is also the
 * owner of the instance).
 */
export function PortfolioEmpty() {
  return (
    <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Nenhuma carteira principal aberta para esta organização ainda.</p>
      <p className="mx-auto mt-2 max-w-2xl text-sm text-fg-muted">
        A carteira principal é única e permanente por organização e é aberta pelo operador, fora desta tela -- não há
        botão aqui que finja abrir uma, porque não existe um segundo caminho de escrita para isso na API.
      </p>
      <details className="mx-auto mt-4 max-w-2xl text-left text-xs text-fg-muted">
        <summary className="cursor-pointer text-fg">Para o operador</summary>
        <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-bg-overlay p-3 text-[11px] text-fg-muted">
          {"uv run python infra/scripts/open_paper_wallet.py \\\n" +
            "  --org <slug> --workspace <slug> --capital-brl 100000 \\\n" +
            "  --fx-source binance.spot.ticker"}
        </pre>
      </details>
    </div>
  );
}
