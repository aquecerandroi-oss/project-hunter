"use server";

import { isApiError } from "@/lib/api-error";
import { getServerSession } from "@/lib/server/auth";

import { getOpportunity, listOpportunities } from "./opportunities";
import type {
  OpportunitiesParams,
  OpportunityDetailOut,
  OpportunityDetailParams,
  OpportunityListPage,
} from "./opportunities-types";

export interface OpportunitiesActionOutcome {
  ok: boolean;
  page: OpportunityListPage;
  reason?: string;
}

function emptyListPage(): OpportunityListPage {
  return { items: [], next_cursor: null };
}

/** Server Action behind `components/opportunities/opportunities-table.tsx`'s "load more" (cursor pagination). */
export async function loadOpportunitiesAction(params: OpportunitiesParams): Promise<OpportunitiesActionOutcome> {
  const session = await getServerSession();
  if (!session) return { ok: false, page: emptyListPage(), reason: "unauthenticated" };

  try {
    const page = await listOpportunities(params);
    return { ok: true, page };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, page: emptyListPage(), reason };
  }
}

export interface OpportunityDetailActionOutcome {
  ok: boolean;
  detail: OpportunityDetailOut | null;
  reason?: string;
}

/**
 * Behind `components/opportunities/why-history.tsx`'s "carregar envelope"
 * button: re-fetches the detail with `include_envelope=true` (capped at
 * `MAX_ENVELOPE_HISTORY_LIMIT` history points) only when the trader actually
 * asks for it -- the plain page load never ships the full recomputation
 * proof for every history point (MF-3, `schemas/opportunities.py`).
 */
export async function loadOpportunityDetailAction(
  id: string,
  params: OpportunityDetailParams,
): Promise<OpportunityDetailActionOutcome> {
  const session = await getServerSession();
  if (!session) return { ok: false, detail: null, reason: "unauthenticated" };

  try {
    const detail = await getOpportunity(id, params);
    return { ok: true, detail };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, detail: null, reason };
  }
}
