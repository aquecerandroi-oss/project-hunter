/**
 * Ausência operacional (docs/DESIGN.md §2): the wallet feature exists and is
 * implemented, there is simply no principal paper wallet open for this
 * organization yet -- opening one is a once-per-organization operator act
 * (D7/ADR 0005, `infra/scripts/open_paper_wallet.py`'s own docstring: "opening
 * one is a once-per-organization act... never a route to a reset"), not
 * something this screen can offer a button for without fabricating a second
 * write path the API does not have. No button that pretends to open a wallet.
 */
export function PortfolioEmpty() {
  return (
    <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Nenhuma carteira principal aberta para esta organização ainda.</p>
      <p className="mx-auto mt-2 max-w-2xl text-sm text-fg-muted">
        A carteira principal é única e permanente por organização (ADR 0005) e é aberta pelo operador, fora desta tela --
        não há botão aqui que finja abrir uma, porque não existe um segundo caminho de escrita para isso na API.
      </p>
      <pre className="mx-auto mt-4 max-w-2xl overflow-x-auto rounded-md border border-border bg-bg-overlay p-3 text-left text-[11px] text-fg-muted">
        {"uv run python infra/scripts/open_paper_wallet.py \\\n" +
          "  --org <slug> --workspace <slug> --capital-brl 100000 \\\n" +
          "  --fx-source binance.spot.ticker"}
      </pre>
    </div>
  );
}
