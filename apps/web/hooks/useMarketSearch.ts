"use client";

import { useEffect, useRef, useState } from "react";

import { searchMarketsAction, type MarketSearchResult } from "@/lib/api/markets-actions";
import { logger } from "@/lib/logger";

/**
 * Minimum characters before a search is ever dispatched (M8, T1.5b fix
 * pass, security): searching on every keystroke with no floor meant each
 * call was a full unpaginated `GET /api/v1/markets` from the web server's
 * single IP, sharing the API's 120/min per-IP rate-limit bucket with all SSR
 * traffic -- a few users typing could 429 everyone's page renders.
 */
export const MARKET_SEARCH_MIN_LENGTH = 2;
const DEBOUNCE_MS = 250;

export type MarketSearchStatus = "idle" | "loading" | "error";

export interface UseMarketSearchResult {
  status: MarketSearchStatus;
  results: MarketSearchResult[];
}

interface SearchState {
  /** The trimmed query these `results`/`status` actually answer -- see `isCurrent` below. */
  forQuery: string;
  status: "loading" | "idle" | "error";
  results: MarketSearchResult[];
}

const EMPTY_SEARCH_STATE: SearchState = { forQuery: "", status: "idle", results: [] };

/**
 * Debounced, race-safe market search behind `components/layout/
 * command-palette.tsx` (extracted out for M9: kept `CommandPaletteBody`
 * under the lint config's per-function complexity budget, and this logic is
 * independently unit-testable). Below `MARKET_SEARCH_MIN_LENGTH` characters
 * this never calls the server action at all -- `status` reads as `"idle"`,
 * never a perpetual "loading".
 */
export function useMarketSearch(query: string): UseMarketSearchResult {
  const [search, setSearch] = useState<SearchState>(EMPTY_SEARCH_STATE);
  const latestQueryRef = useRef("");

  useEffect(() => {
    const trimmed = query.trim();
    latestQueryRef.current = trimmed;
    if (trimmed.length < MARKET_SEARCH_MIN_LENGTH) return undefined;

    // `setSearch` below only ever runs inside this deferred timeout (and its
    // own `.then()`/`.catch()`), never synchronously in the effect body
    // itself -- the debounce IS the "subscribe, react later to an external
    // event" the set-state-in-effect rule asks for.
    const handle = setTimeout(() => {
      setSearch({ forQuery: trimmed, status: "loading", results: [] });
      searchMarketsAction(trimmed)
        .then((outcome) => {
          // A slower, older request must never overwrite a faster, newer one
          // (T1.5b Astra must-fix #2): a stale, still-resolving response
          // from a PREVIOUS query must never become actionable again.
          if (latestQueryRef.current !== trimmed) return;
          if (!outcome.ok) {
            logger.warn("command_palette_search_failed", { reason: outcome.reason });
            setSearch({ forQuery: trimmed, status: "error", results: [] });
            return;
          }
          setSearch({ forQuery: trimmed, status: "idle", results: outcome.results });
        })
        .catch((error: unknown) => {
          if (latestQueryRef.current !== trimmed) return;
          logger.warn("command_palette_search_threw", { error: String(error) });
          setSearch({ forQuery: trimmed, status: "error", results: [] });
        });
    }, DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [query]);

  const trimmedQuery = query.trim();
  const tooShortToSearch = trimmedQuery.length < MARKET_SEARCH_MIN_LENGTH;
  // The search state is only trusted for the query it actually answers --
  // the instant the input changes again, yesterday's results stop being
  // shown until a fresh response for the new query lands.
  const isCurrent = search.forQuery === trimmedQuery;
  const status: MarketSearchStatus = tooShortToSearch ? "idle" : isCurrent ? search.status : "loading";
  const results = tooShortToSearch || !isCurrent ? [] : search.results;

  return { status, results };
}
