/**
 * Shared search bounds for the markets command palette. Kept outside the
 * `"use server"` module (`markets-actions.ts`): Next.js only allows async
 * functions to be exported from a server-action file.
 */

/** Matches `GET /api/v1/markets` documented `q` `max_length=64`. */
export const MARKET_SEARCH_MAX_LENGTH = 64;
