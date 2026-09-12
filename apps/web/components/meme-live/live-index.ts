/**
 * T4.17 deliverable 4: the paper loop keeps filling a `mode: "live"`
 * proposal in shadow (`docs/RISK_ENGINE_MEME.md`, T4.14 note), so the same
 * `proposal_id` can own both a paper bet (`meme-desk`) and a real order/
 * position (`meme-live`). Pure indexing, no React -- `tests/meme-live-labels.test.ts`.
 */
import type { LiveOrder, LivePosition, MemeLive } from "@/lib/api/meme-live-types";

export interface LiveOutcome {
  position: LivePosition | null;
  /** The most recent order for this proposal (`received_at` desc) -- the buy attempt when there is no position yet. */
  order: LiveOrder | null;
}

export type LiveOutcomeIndex = ReadonlyMap<string, LiveOutcome>;

/** One entry per `proposal_id` seen in either list -- a proposal with only a refused order (no position) still gets an entry, so "sombra de uma ordem REAL" can show the refusal instead of silence. */
export function buildLiveOutcomeIndex(live: MemeLive | null | undefined): LiveOutcomeIndex {
  const index = new Map<string, LiveOutcome>();
  if (!live) return index;

  const ordersByProposal = new Map<string, LiveOrder[]>();
  for (const order of live.orders) {
    const list = ordersByProposal.get(order.proposal_id) ?? [];
    list.push(order);
    ordersByProposal.set(order.proposal_id, list);
  }

  for (const position of live.positions) {
    index.set(position.proposal_id, { position, order: null });
  }
  for (const [proposalId, orders] of ordersByProposal) {
    const newest = orders.reduce((latest, order) => (order.received_at > latest.received_at ? order : latest));
    const existing = index.get(proposalId);
    index.set(proposalId, { position: existing?.position ?? null, order: newest });
  }
  return index;
}
