/**
 * TypeScript aliases onto the OpenAPI-generated `components["schemas"]` for
 * the Meme Radar (T4.3, `apps/api/hunter_api/{routers,schemas}/meme.py`) --
 * same pattern as `lib/api/portfolio-types.ts`. Every `Decimal` field the API
 * sends stays a `string` here (never `number` -- CLAUDE.md: money/reserves
 * are never `float`).
 */
import type { components } from "@hunter/shared-types/api";

export type MemeOverview = components["schemas"]["MemeOverviewOut"];
export type MemeOverviewSource = MemeOverview["source"];
export type OverviewByMode = components["schemas"]["OverviewByModeOut"];
export type OverviewWindowCount = components["schemas"]["OverviewWindowCountOut"];
export type Graduations = components["schemas"]["GraduationsOut"];

export type MemeToken = components["schemas"]["MemeTokenOut"];
export type MemeTokenState = MemeToken["state"];
export type MemeSource = NonNullable<MemeToken["snapshot_source"]>;
export type MemeTokenList = components["schemas"]["MemeTokenListOut"];

export type MemeSnapshotPoint = components["schemas"]["MemeSnapshotPointOut"];
export type MemeFeaturePoint = components["schemas"]["MemeFeaturePointOut"];
export type MemeNullReason = NonNullable<MemeFeaturePoint["progress_reason"]>;
export type MemeTokenDetail = components["schemas"]["MemeTokenDetailOut"];

export type MemeGap = components["schemas"]["MemeGapOut"];
export type MemeGapStream = MemeGap["stream"];
export type MemeGapList = components["schemas"]["MemeGapListOut"];

export type MemeTokenSort = "mcap" | "age" | "progress";
export const MEME_TOKEN_SORTS: readonly MemeTokenSort[] = ["mcap", "age", "progress"];

/** Mirrors `hunter_api.schemas.meme.MEME_LABEL`'s literal default -- used by the "empty page" fallbacks in `lib/api/meme-actions.ts` (a client-side placeholder never actually shown, since it only appears when a Server Action's own auth/network guard already short-circuits before any real payload exists). */
export const MEME_LABEL = "Meme Radar — só monitoramento, nunca execução (pump.fun)";
