/**
 * TypeScript aliases onto the OpenAPI-generated `components["schemas"]` for
 * the operator desk (T4.7, `apps/api/hunter_api/{routers,schemas}/meme_desk.py`)
 * -- same pattern as `lib/api/meme-types.ts`. Every `Decimal` the API sends
 * stays a `string` here (CLAUDE.md: money is never a float).
 *
 * The API types `status`/`origin`/`exit_reason` as "the contract's enum or
 * any string" (the loop, T4.6, is the writer of most of those columns), so
 * the generated type is `string`; the narrow unions below are what the
 * screen labels, with a guard for anything else (never a raw enum on screen,
 * DESIGN-5).
 */
import type { components } from "@hunter/shared-types/api";

export type MemeDesk = components["schemas"]["DeskListOut"];
export type MemeDeskRow = components["schemas"]["DeskRowOut"];
export type MemeDeskBet = components["schemas"]["BetOut"];
export type MemeDeskQuote = components["schemas"]["QuoteOut"];
export type MemeDeskParams = components["schemas"]["DeskParamsOut"];
export type MemeDeskSummary = components["schemas"]["DeskSummaryOut"];
export type MemeDeskRuleSetBalance = components["schemas"]["RuleSetBalanceOut"];
export type MemeDeskSolUsd = components["schemas"]["SolUsdQuoteOut"];
export type MemeDeskCommand = components["schemas"]["CommandOut"];
export type MemeDeskProposalOut = components["schemas"]["ProposalOut"];
export type MemeDeskApproveBody = components["schemas"]["ApproveProposalIn"];
export type MemeDeskRejectBody = components["schemas"]["RejectProposalIn"];
export type MemeDeskManualBody = components["schemas"]["ManualProposalIn"];

export type MemeProposalStatus = "proposed" | "approved" | "rejected" | "expired" | "filled" | "unfilled";
export const MEME_PROPOSAL_STATUSES: readonly MemeProposalStatus[] = ["proposed", "approved", "rejected", "expired", "filled", "unfilled"];

// T4.13: `max_loss` (the loop's loss floor, written since T4.6) and
// `line_broken` (0026, T4.10) joined the API's `ExitReason`; a label missing
// here is exactly what broke three production builds on 2026-09-12.
export type MemeExitReason = "target" | "trailing" | "time_stop" | "migrated" | "creator_dump" | "sell_now" | "rug_no_snapshot" | "max_loss" | "line_broken";
export const MEME_EXIT_REASONS: readonly MemeExitReason[] = ["target", "trailing", "time_stop", "migrated", "creator_dump", "sell_now", "rug_no_snapshot", "max_loss", "line_broken"];

export function isMemeProposalStatus(value: string): value is MemeProposalStatus {
  return (MEME_PROPOSAL_STATUSES as readonly string[]).includes(value);
}

export function isMemeExitReason(value: string): value is MemeExitReason {
  return (MEME_EXIT_REASONS as readonly string[]).includes(value);
}

// T4.10b: `meme_paper_bets.leg` / `parent_bet_id` (brief T4.10 §Conjuntos de
// regras -- the hype probe and its second leg). Read tolerantly off the bet
// object: the backend lands these columns in parallel, so a payload from
// before them yields `null`, never a crash and never a raw value on screen.
export type MemeBetLeg = "probe" | "scale" | "single";
export const MEME_BET_LEGS: readonly MemeBetLeg[] = ["probe", "scale", "single"];

export function isMemeBetLeg(value: string): value is MemeBetLeg {
  return (MEME_BET_LEGS as readonly string[]).includes(value);
}

export interface MemeBetLegReading {
  leg: MemeBetLeg | null;
  parentBetId: string | null;
}

export function readBetLeg(bet: object): MemeBetLegReading {
  const record = bet as Record<string, unknown>;
  const leg = typeof record.leg === "string" && isMemeBetLeg(record.leg) ? record.leg : null;
  const parent = record.parent_bet_id;
  return { leg, parentBetId: typeof parent === "string" && parent.length > 0 ? parent : null };
}

/** Mirrors `hunter_api.schemas.meme_desk.MEME_DESK_LABEL` -- the permanent label (contract §Tela). */
export const MEME_DESK_LABEL = "PAPEL — nenhuma transação real; a chave e a flag ao vivo não existem neste processo";

/** `/api/v1/orgs/{org_id}/meme` -- shared by the server-only GET module and the "use server" write actions. */
export function memeDeskBase(orgId: string): string {
  return `/api/v1/orgs/${orgId}/meme`;
}

/**
 * The loop's liveness, read defensively off `GET /meme/lab` (T4.6, built in
 * parallel -- its shape is not frozen in the contract beyond
 * `sources.lab_last_tick_at`, contract §Semântica 5). `reason` names why
 * there is no reading, so the strip can say "laço: sem leitura" instead of
 * pretending the loop is stopped or alive.
 */
export interface MemeLoopState {
  lastTickAt: string | null;
  reason: "endpoint_missing" | "read_failed" | "shape_unknown" | null;
}
