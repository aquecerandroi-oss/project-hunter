"use client";

import { useEffect, useRef, useState } from "react";

import { searchSpotMarketsAction, type SpotMarketOption } from "@/lib/api/markets-actions";
import { logger } from "@/lib/logger";

/** Mirrors `useMarketSearch.ts`'s own floor (M8): no call below this many characters. */
export const SPOT_MARKET_SEARCH_MIN_LENGTH = 2;
const DEBOUNCE_MS = 250;

export type SpotMarketSearchStatus = "idle" | "loading" | "error";

export interface UseSpotMarketSearchResult {
  status: SpotMarketSearchStatus;
  results: SpotMarketOption[];
}

interface SearchState {
  forQuery: string;
  status: "loading" | "idle" | "error";
  results: SpotMarketOption[];
}

const EMPTY_SEARCH_STATE: SearchState = { forQuery: "", status: "idle", results: [] };

/**
 * Debounced, race-safe SPOT market search behind
 * `components/portfolio/manual-order-market-field.tsx` (T3.72) -- the same
 * shape as `useMarketSearch.ts` (command palette), a distinct hook because
 * the result carries the richer `SpotMarketOption` fields (volume, 50M floor
 * material) the palette's bare `{exchange, symbol}` does not.
 */
export function useSpotMarketSearch(query: string): UseSpotMarketSearchResult {
  const [search, setSearch] = useState<SearchState>(EMPTY_SEARCH_STATE);
  const latestQueryRef = useRef("");

  useEffect(() => {
    const trimmed = query.trim();
    latestQueryRef.current = trimmed;
    if (trimmed.length < SPOT_MARKET_SEARCH_MIN_LENGTH) return undefined;

    const handle = setTimeout(() => {
      setSearch({ forQuery: trimmed, status: "loading", results: [] });
      searchSpotMarketsAction(trimmed)
        .then((outcome) => {
          if (latestQueryRef.current !== trimmed) return;
          if (!outcome.ok) {
            logger.warn("spot_market_search_failed", { reason: outcome.reason });
            setSearch({ forQuery: trimmed, status: "error", results: [] });
            return;
          }
          setSearch({ forQuery: trimmed, status: "idle", results: outcome.results });
        })
        .catch((error: unknown) => {
          if (latestQueryRef.current !== trimmed) return;
          logger.warn("spot_market_search_threw", { error: String(error) });
          setSearch({ forQuery: trimmed, status: "error", results: [] });
        });
    }, DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [query]);

  const trimmedQuery = query.trim();
  const tooShortToSearch = trimmedQuery.length < SPOT_MARKET_SEARCH_MIN_LENGTH;
  const isCurrent = search.forQuery === trimmedQuery;
  const status: SpotMarketSearchStatus = tooShortToSearch ? "idle" : isCurrent ? search.status : "loading";
  const results = tooShortToSearch || !isCurrent ? [] : search.results;

  return { status, results };
}
