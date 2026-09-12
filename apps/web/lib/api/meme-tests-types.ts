/**
 * TypeScript aliases onto the OpenAPI-generated `components["schemas"]` for
 * the test record (T4.13, `apps/api/hunter_api/{routers,schemas}/meme_tests.py`)
 * -- same pattern as `lib/api/meme-desk-types.ts`. Every `Decimal` the API
 * sends stays a `string` here (CLAUDE.md: money is never a float).
 *
 * The narrow unions below are the closed vocabularies the screen labels
 * (`components/meme-tests/labels.ts`), each with a guard so a value the API
 * adds before this file learns it renders as "não previsto", never raw.
 */
import type { components } from "@hunter/shared-types/api";

export type MemeTests = components["schemas"]["TestsListOut"];
export type MemeTestRow = components["schemas"]["TestRowOut"];
export type MemeTestEntry = components["schemas"]["TestEntryOut"];
export type MemeTestExit = components["schemas"]["TestExitOut"];
export type MemeTestLabContext = components["schemas"]["LabContextOut"];
export type MemeTestRuleSet = components["schemas"]["TestRuleSetOut"];
export type MemeTestsTotals = components["schemas"]["TestsTotalsOut"];
export type MemeTestsSources = components["schemas"]["TestsSourcesOut"];
export type MemeTestDetail = components["schemas"]["TestDetailOut"];
export type MemeTestCurvePoint = components["schemas"]["TestCurvePointOut"];

export type MemeTestKind = MemeTestRow["kind"];
export const MEME_TEST_KINDS: readonly MemeTestKind[] = ["paper", "real_observed"];

export type MemeWalletsSource = MemeTestsSources["wallets"];
export const MEME_WALLETS_SOURCES: readonly MemeWalletsSource[] = ["observada", "não observada", "leitura indisponível"];

export type MemePnlUsdBasis = NonNullable<MemeTestRow["pnl_usd_basis"]>;
export const MEME_PNL_USD_BASES: readonly MemePnlUsdBasis[] = ["exit_quote", "entry_quote_provisional"];

export type MemePnlUsdReason = NonNullable<MemeTestRow["pnl_usd_reason"]>;
export const MEME_PNL_USD_REASONS: readonly MemePnlUsdReason[] = ["no_exit_quote", "no_entry_quote", "no_pnl"];

export type MemeLabContextReason = NonNullable<MemeTestLabContext["reason"]>;
export const MEME_LAB_CONTEXT_REASONS: readonly MemeLabContextReason[] = ["manual_no_minute", "no_features_row"];

export function isMemeTestKind(value: string): value is MemeTestKind {
  return (MEME_TEST_KINDS as readonly string[]).includes(value);
}

/** Mirrors `hunter_api.schemas.meme_tests.REAL_OBSERVED_LABEL` (brief T4.12 §3, verbatim). */
export const REAL_OBSERVED_LABEL = "REAL — observado na cadeia, não executado por este sistema";
