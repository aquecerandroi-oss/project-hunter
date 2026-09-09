import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { RadarCoverageOut } from "./radar-coverage-types";

/**
 * `GET /api/v1/radar/coverage` (`apps/api/hunter_api/routers/radar.py`,
 * T3.46) -- global, not tenant-scoped, one read per page load (Radar and
 * Opportunities both render the "Estado do Radar" strip from this, never
 * from the 5s `useRadarPage` reconciliation loop: this is a diagnostic
 * snapshot of how much of the Radar exists, not a row that needs to move in
 * real time).
 */
export async function getRadarCoverage(): Promise<RadarCoverageOut> {
  return apiFetch<RadarCoverageOut>("/api/v1/radar/coverage");
}
