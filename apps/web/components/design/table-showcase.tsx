import { ROW_HEIGHT_BY_DENSITY, type Density } from "@/hooks/useDensity";

const ROWS = [
  { symbol: "BTC/USDT", price: "64.230,50", change: "+1,84%", positive: true },
  { symbol: "ETH/USDT", price: "3.128,10", change: "-0,62%", positive: false },
  { symbol: "SOL/USDT", price: "142,75", change: "+3,05%", positive: true },
] as const;

function DensityTable({ density }: { density: Density }) {
  const rowHeight = ROW_HEIGHT_BY_DENSITY[density];
  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs uppercase tracking-wide text-fg-muted">
        {density === "comfortable" ? "Confortável" : "Compacta"} ({rowHeight}px)
      </p>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-left">
          <thead className="bg-bg-overlay text-xs text-fg-muted">
            <tr>
              <th style={{ height: 32 }} className="px-3 font-medium">
                Par
              </th>
              <th style={{ height: 32 }} className="px-3 text-right font-medium">
                Preço
              </th>
              <th style={{ height: 32 }} className="px-3 text-right font-medium">
                Variação 24h
              </th>
            </tr>
          </thead>
          <tbody className="text-[13px]">
            {ROWS.map((row) => (
              <tr key={row.symbol} style={{ height: rowHeight }} className="border-t border-border">
                <td className="px-3 text-fg">{row.symbol}</td>
                <td className="num px-3 text-right text-fg">{row.price}</td>
                <td className={`num px-3 text-right ${row.positive ? "text-green" : "text-red"}`}>{row.change}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * Dense table anchor (docs/DESIGN.md §2, T1.5b joint decision #6): 40px rows
 * comfortable / 32px compact, 13px body, right-aligned tabular numbers with
 * explicit sign and semantic color. Both densities rendered side by side so
 * `ROW_HEIGHT_BY_DENSITY` (`hooks/useDensity.ts`) is visibly the one number
 * driving both the CSS height and the real table's virtualization math.
 */
export function TableShowcase() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <DensityTable density="comfortable" />
      <DensityTable density="compact" />
    </div>
  );
}
