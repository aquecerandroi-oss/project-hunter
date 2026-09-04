import "server-only";

import type { Problem } from "@hunter/shared-types";
import type { components } from "@hunter/shared-types/api";

import { ApiError } from "@/lib/api-error";

/**
 * Aliases onto the OpenAPI-generated `components["schemas"]` (T09 -- see
 * `infra/scripts/dump_openapi.py` and root `pnpm gen:types`). Every response
 * shape a Server Component or Server Action needs is named here once so
 * call sites read `OrganizationOut` instead of the generated path.
 */
export type OrganizationOut = components["schemas"]["OrganizationOut"];
export type OrganizationCreated = components["schemas"]["OrganizationCreated"];
export type WorkspaceOut = components["schemas"]["WorkspaceOut"];
export type MemberOut = components["schemas"]["MemberOut"];
export type InvitationOut = components["schemas"]["InvitationOut"];
export type InvitationCreated = components["schemas"]["InvitationCreated"];
export type MeOut = components["schemas"]["MeOut"];
export type MembershipOut = components["schemas"]["MembershipOut"];
export type OnboardingState = components["schemas"]["OnboardingState"];
export type AuditEntryOut = components["schemas"]["AuditEntryOut"];
export type OrganizationRole = components["schemas"]["OrganizationRole"];
export type WorkspaceObjective = components["schemas"]["WorkspaceObjective"];
export type RiskPreset = components["schemas"]["RiskPreset"];

export type Page<T> = { items: T[]; next_cursor?: string | null };
export type ListParams = { limit?: number; cursor?: string };

/**
 * `/ready` and `/api/v1/system/info` (apps/api/hunter_api/health.py) return
 * plain dicts, not a Pydantic `response_model`, so the generated OpenAPI
 * types can't describe their shape (see the module docstring below for why
 * -- `dump_openapi.py` can't fabricate what the API itself doesn't declare).
 * These mirror `health.py`'s actual return values by hand.
 */
export interface ReadyStatus {
  database: boolean;
  redis: boolean;
  database_detail?: string;
  redis_detail?: string;
}

export interface SystemInfo {
  environment: string;
  version: string;
  git_sha: string;
  features: {
    enable_live_trading: boolean;
    enable_social_intelligence: boolean;
    enable_onchain: boolean;
    enable_stripe: boolean;
    enable_llm_analysis: boolean;
    enable_arena: boolean;
    enable_backtests: boolean;
  };
}

/**
 * Every mutation goes through a Server Action shaped like this instead of
 * throwing to the client -- a form can render `problem.detail` without a
 * try/catch, and a thrown `ApiError` never crosses the server/client
 * boundary (Next.js would otherwise turn it into an opaque digest).
 */
export type ActionResult<T = undefined> = { ok: true; data: T } | { ok: false; problem: Problem };

export function actionOk<T>(data: T): ActionResult<T> {
  return { ok: true, data };
}

export function actionError(problem: Problem): ActionResult<never> {
  return { ok: false, problem };
}

/** Turns a thrown `ApiError` (lib/api-error.ts) into the RFC 9457 shape Server Actions return. */
export function problemFromApiError(error: ApiError): Problem {
  return {
    type: error.type,
    title: error.message,
    status: error.status,
    detail: error.detail,
    instance: error.instance,
  };
}

/** A synthetic problem for a client-side (zod) validation failure -- never reaches `apps/api`. */
export function validationProblem(detail: string): Problem {
  return {
    type: "https://hunter.dev/problems/validation-error",
    title: "Validation Error",
    status: 422,
    detail,
  };
}

export { ApiError };
