"use server";

import { isApiError } from "@/lib/api-error";
import { getLabSignals, type LabSignalsParams } from "@/lib/api/lab";
import { listMarkets } from "@/lib/api/markets";
import { getServerSession } from "@/lib/server/auth";

import type { LabSignalsPage } from "./lab-types";

export interface LabSignalsActionOutcome {
  ok: boolean;
  page: LabSignalsPage;
  reason?: string;
}

const EMPTY_PAGE: LabSignalsPage = { items: [], next_cursor: null };

/**
 * Server Action behind `components/lab/lab-signals-table.tsx`'s "load more"
 * (cursor pagination) and filter changes: `lib/api/lab.ts` is
 * `"server-only"`, so the client table cannot call `getLabSignals` directly
 * (ESLint boundary: `components/**` never imports `@/lib/server/**`, and
 * `apiFetch` lives there). Fails closed on a missing session before ever
 * reaching the API, mirroring `markets-actions.ts::searchMarketsAction`.
 */
export async function loadLabSignalsAction(params: LabSignalsParams): Promise<LabSignalsActionOutcome> {
  const session = await getServerSession();
  if (!session) return { ok: false, page: EMPTY_PAGE, reason: "unauthenticated" };

  try {
    const page = await getLabSignals(params);
    return { ok: true, page };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, page: EMPTY_PAGE, reason };
  }
}

export interface LabEnvelopeActionOutcome {
  ok: boolean;
  envelope: Record<string, unknown> | null;
  reason?: string;
}

/**
 * Fetches one signal's full envelope on demand (`?include=envelope`,
 * SHADOW-LAB.md §2's immutable `supporting_features`) -- the list endpoint
 * omits it by default because it can be large and is redundant for most of
 * the table's uses (contract-S3-lab.md). Re-queries by the same filters plus
 * `strategy_version_id`+cursor is not available per-signal, so this instead
 * asks for a single-item page filtered down to just that signal's market and
 * scans for the matching id -- the API has no `GET /signals/{id}`, and this
 * brief's allowed files do not include adding one.
 */
export async function loadLabSignalEnvelopeAction(
  signalId: string,
  market: string,
  strategyVersionId: string,
  cohort: string,
): Promise<LabEnvelopeActionOutcome> {
  const session = await getServerSession();
  if (!session) return { ok: false, envelope: null, reason: "unauthenticated" };

  try {
    const page = await getLabSignals({
      market,
      strategy_version_id: strategyVersionId,
      cohort,
      include: ["envelope"],
      limit: 200,
    });
    const match = page.items.find((item) => item.signal_id === signalId);
    if (!match) return { ok: false, envelope: null, reason: "sinal não encontrado nesta página" };
    return { ok: true, envelope: match.supporting_features };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, envelope: null, reason };
  }
}

/**
 * `SignalListItemOut.market` is a bare symbol (`Market.symbol`, no exchange
 * -- `repositories/lab_signals.py`'s query never selects `Market.exchange`),
 * so this page cannot build a `/markets/[exchange]/[symbol]` link from the
 * signals response alone without guessing the exchange, which risks
 * pointing at the wrong row if the same symbol is ever listed on more than
 * one exchange (CLAUDE.md: no invented data). This resolves the real
 * exchange via the already-implemented, already-tested `listMarkets({ q })`
 * (`lib/api/markets.ts`, T1.4) -- exactly one match routes straight to the
 * market detail page; anything else (zero or several matches) falls back to
 * the markets search results, which is still a real, honest page.
 */
export async function resolveMarketHrefAction(orgSlug: string, symbol: string): Promise<string> {
  const searchFallback = `/${orgSlug}/markets?q=${encodeURIComponent(symbol)}`;
  const session = await getServerSession();
  if (!session) return searchFallback;

  try {
    // No `monitored` filter: a market the Shadow Lab evaluated may no longer
    // be in the currently-monitored universe, and `monitored: false` would
    // wrongly exclude a market that still IS monitored (`Market.is_monitored
    // .is_(monitored)` in `repositories/markets.py` filters both ways).
    const page = await listMarkets({ q: symbol, limit: 10 });
    const exact = page.items.filter((item) => item.symbol === symbol);
    const match = exact.length === 1 ? exact[0] : undefined;
    if (!match) return searchFallback;
    return `/${orgSlug}/markets/${encodeURIComponent(match.exchange)}/${encodeURIComponent(match.symbol)}`;
  } catch {
    return searchFallback;
  }
}
