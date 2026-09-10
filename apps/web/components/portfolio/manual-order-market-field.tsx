"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { floorMet, ManualOrderMarketChip } from "@/components/portfolio/manual-order-market-chip";
import { SPOT_MARKET_SEARCH_MIN_LENGTH, useSpotMarketSearch } from "@/hooks/useSpotMarketSearch";
import type { SpotMarketOption } from "@/lib/api/markets-actions";
import { formatCompact } from "@/lib/format";

export interface ManualOrderMarketFieldProps {
  value: SpotMarketOption | null;
  onChange: (market: SpotMarketOption | null) => void;
  disabled?: boolean;
}

/**
 * The SPOT market picker for "Nova ordem paper" (brief item 1): search over
 * `?market_type=spot` (`useSpotMarketSearch`), each result showing its 24h
 * volume and 50M floor state -- never inventing a floor state for a market
 * whose volume the API did not send (`floorMet` returns `null`, rendered as
 * "volume indisponível", not a guessed badge).
 */
export function ManualOrderMarketField({ value, onChange, disabled = false }: ManualOrderMarketFieldProps) {
  const [query, setQuery] = useState("");
  const { status, results } = useSpotMarketSearch(query);
  const tooShort = query.trim().length < SPOT_MARKET_SEARCH_MIN_LENGTH;

  if (value) {
    return (
      <ManualOrderMarketChip
        market={value}
        disabled={disabled}
        onClear={() => {
          onChange(null);
          setQuery("");
        }}
      />
    );
  }

  return (
    <div>
      <Input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Buscar par SPOT (ex.: BTCUSDT)"
        aria-label="Buscar mercado SPOT"
        disabled={disabled}
        className="w-full"
      />
      {!tooShort && (
        <ul className="mt-1 max-h-48 overflow-y-auto rounded-md border border-border">
          {status === "loading" && <li className="px-3 py-2 text-sm text-fg-muted">Buscando...</li>}
          {status === "error" && <li className="px-3 py-2 text-sm text-red">Busca indisponível. Tente novamente.</li>}
          {status === "idle" && results.length === 0 && (
            <li className="px-3 py-2 text-sm text-fg-muted">Nenhum mercado SPOT encontrado para &quot;{query}&quot;.</li>
          )}
          {results.map((result) => {
            const met = floorMet(result.volume_24h);
            return (
              <li key={`${result.exchange}:${result.symbol}`}>
                <button
                  type="button"
                  onClick={() => onChange(result)}
                  className="flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left text-sm hover:bg-bg-overlay"
                >
                  <span className="font-medium">{result.symbol}</span>
                  <span className="text-xs text-fg-muted">{result.exchange}</span>
                  <span className="font-mono text-xs tabular-nums text-fg-muted">
                    {result.volume_24h !== null ? `${formatCompact(result.volume_24h)} ${result.quote_asset ?? ""}`.trim() : "volume indisponível"}
                  </span>
                  {met !== null && <Badge variant={met ? "positive" : "warning"}>{met ? "acima do piso" : "abaixo do piso"}</Badge>}
                  {!result.is_monitored && <Badge variant="outline">fora do universo monitorado</Badge>}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
