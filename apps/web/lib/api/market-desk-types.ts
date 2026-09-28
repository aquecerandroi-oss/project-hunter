/**
 * Aliases onto the T4.82 confluence-screen contract
 * (`apps/api/hunter_api/{routers,schemas}/market_desk.py`) -- the `spot/1`
 * desk trail for one market. Same convention as `lib/api/meme-desk-types.ts`:
 * every `Decimal` the API sends stays a `string` here (CLAUDE.md: money is
 * never a float).
 */
import type { components } from "@hunter/shared-types/api";

export type DeskMarketOut = components["schemas"]["DeskMarketOut"];
export type DeskOrderOut = components["schemas"]["DeskOrderOut"];
export type DeskPositionOut = components["schemas"]["DeskPositionOut"];
export type DeskOut = components["schemas"]["DeskOut"];

/** `spot_orders.status` -- design §4A's three answers ("recusada" / an execution / "sem registro"). */
export type DeskOrderStatus = "admitted" | "confirmed" | "refused" | "failed";

/** `/api/v1/orgs/{org_id}/markets` -- shared by every reader under this router. */
export function marketDeskOrgBase(orgId: string): string {
  return `/api/v1/orgs/${orgId}/markets`;
}
