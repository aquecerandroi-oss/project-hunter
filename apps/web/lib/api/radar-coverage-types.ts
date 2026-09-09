/**
 * TypeScript aliases onto the OpenAPI-generated `components["schemas"]` for
 * `GET /api/v1/radar/coverage` (`apps/api/hunter_api/routers/radar.py`,
 * `schemas/radar_coverage.py`, T3.46 -- `.claude/state/notes-T3.46.md`).
 * Same pattern as `lib/api/radar-types.ts`.
 */
import type { components } from "@hunter/shared-types/api";

export type RadarCoverageOut = components["schemas"]["RadarCoverageOut"];
export type RadarDetectorOut = components["schemas"]["RadarDetectorOut"];
