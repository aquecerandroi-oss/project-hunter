const ROWS = [
  { symbol: "BTC/USDT", price: "64.230,50", change: "+1,84%", positive: true },
  { symbol: "ETH/USDT", price: "3.128,10", change: "-0,62%", positive: false },
  { symbol: "SOL/USDT", price: "142,75", change: "+3,05%", positive: true },
] as const;

/** Dense table anchor (docs/DESIGN.md §2): 32px rows, 13px body, right-aligned tabular numbers with explicit sign and semantic color. */
export function TableShowcase() {
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-left">
        <thead className="bg-bg-overlay text-xs text-fg-muted">
          <tr>
            <th className="h-8 px-3 font-medium">Par</th>
            <th className="h-8 px-3 text-right font-medium">Preço</th>
            <th className="h-8 px-3 text-right font-medium">Variação 24h</th>
          </tr>
        </thead>
        <tbody className="text-[13px]">
          {ROWS.map((row) => (
            <tr key={row.symbol} className="h-8 border-t border-border">
              <td className="px-3 text-fg">{row.symbol}</td>
              <td className="num px-3 text-right text-fg">{row.price}</td>
              <td className={`num px-3 text-right ${row.positive ? "text-green" : "text-red"}`}>{row.change}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
