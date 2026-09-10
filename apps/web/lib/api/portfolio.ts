import "server-only";

import { apiFetch } from "@/lib/server/api";

import type {
  AsOfPage,
  CursorPage,
  EquityCurvePoint,
  KillSwitchDetail,
  OrderRow,
  PortfolioAnchor,
  PortfolioListItem,
  PortfolioSummary,
  PortfolioTradeRow,
  PositionRow,
  RiskLimits,
} from "./portfolio-types";

/**
 * `GET /api/v1/orgs/{org_id}/portfolios/**` (T3.8a, `routers/portfolio.py` +
 * `routers/risk.py`) -- tenant-scoped reads for the T3.8b wallet screen. Every
 * function here is `"server-only"` (same boundary as `lib/api/lab.ts`); no
 * mutation lives in this file because T3.8b is the read half of T3.8 (the
 * manual paper order and the kill switch resume are a separate admission path,
 * `docs/plans/M3.md` T3.12/T3.14, out of this brief).
 */
function portfoliosBase(orgId: string): string {
  return `/api/v1/orgs/${orgId}/portfolios`;
}

export interface ListPortfoliosParams {
  limit?: number;
  cursor?: string;
}

function listQuery(params: ListPortfoliosParams): string {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** Every live wallet of the organization -- today, at most the paper principal (T3.8a docstring). */
export async function listPortfolios(orgId: string, params: ListPortfoliosParams = {}): Promise<CursorPage<PortfolioListItem>> {
  return apiFetch<CursorPage<PortfolioListItem>>(`${portfoliosBase(orgId)}${listQuery(params)}`);
}

/** One wallet: equity, cash, reserves, BRL decomposition and risk state, all at one `as_of`. */
export async function getPortfolioSummary(orgId: string, portfolioId: string): Promise<PortfolioSummary> {
  return apiFetch<PortfolioSummary>(`${portfoliosBase(orgId)}/${portfolioId}`);
}

/** The wallet's opening conversion (BRL → USDT), written once at open time -- never recomputed. */
export async function getPortfolioAnchor(orgId: string, portfolioId: string): Promise<PortfolioAnchor> {
  return apiFetch<PortfolioAnchor>(`${portfoliosBase(orgId)}/${portfolioId}/anchor`);
}

export interface EquityCurveParams {
  resolution?: string;
  from?: string;
  to?: string;
  limit?: number;
  cursor?: string;
}

function equityCurveQuery(params: EquityCurveParams): string {
  const search = new URLSearchParams();
  if (params.resolution !== undefined) search.set("resolution", params.resolution);
  if (params.from !== undefined) search.set("from", params.from);
  if (params.to !== undefined) search.set("to", params.to);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * The equity curve, in USDT and BRL (or a reason per point). Ascending by
 * `ts` (`services/portfolio_lists.py::list_equity_curve`), so a first,
 * unpaginated `limit`-sized page is the *oldest* points, not necessarily the
 * most recent -- acceptable while the wallet is new enough that its whole
 * history fits in one page (`MAX_PAGE_SIZE = 200`); revisit with `from`/`to`
 * once a wallet's curve outgrows it.
 */
export async function getEquityCurve(
  orgId: string,
  portfolioId: string,
  params: EquityCurveParams = {},
): Promise<AsOfPage<EquityCurvePoint>> {
  return apiFetch<AsOfPage<EquityCurvePoint>>(`${portfoliosBase(orgId)}/${portfolioId}/equity-curve${equityCurveQuery(params)}`);
}

export interface ActivityListParams {
  limit?: number;
  cursor?: string;
}

function activityQuery(params: ActivityListParams): string {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** Open/closing/closed positions -- honestly empty until T3.4/T3.5 land a writer. */
export async function getPositions(orgId: string, portfolioId: string, params: ActivityListParams = {}): Promise<AsOfPage<PositionRow>> {
  return apiFetch<AsOfPage<PositionRow>>(`${portfoliosBase(orgId)}/${portfolioId}/positions${activityQuery(params)}`);
}

/** Orders (entry/stop/target/exit/reduce) -- honestly empty until T3.4/T3.5 land a writer. */
export async function getOrders(orgId: string, portfolioId: string, params: ActivityListParams = {}): Promise<AsOfPage<OrderRow>> {
  return apiFetch<AsOfPage<OrderRow>>(`${portfoliosBase(orgId)}/${portfolioId}/orders${activityQuery(params)}`);
}

/** Closed trades with realized PnL -- honestly empty until T3.4/T3.5 land a writer. */
export async function getTrades(orgId: string, portfolioId: string, params: ActivityListParams = {}): Promise<AsOfPage<PortfolioTradeRow>> {
  return apiFetch<AsOfPage<PortfolioTradeRow>>(`${portfoliosBase(orgId)}/${portfolioId}/trades${activityQuery(params)}`);
}

/**
 * The wallet's kill switch, with its motive and evidence
 * (`routers/risk.py::read_kill_switch`) -- the fuller read than
 * `PortfolioSummary.risk_state.kill_switch`, see `KillSwitchDetail`'s own
 * docstring in `portfolio-types.ts` for why this screen uses this one for
 * the kill switch section specifically.
 */
export async function getKillSwitch(orgId: string, portfolioId: string): Promise<KillSwitchDetail> {
  return apiFetch<KillSwitchDetail>(`${portfoliosBase(orgId)}/${portfolioId}/risk/kill-switch`);
}

/**
 * `GET .../risk/limits` (`routers/risk.py::read_risk_limits`) -- the numeric
 * `paper_v1` preset (T3.72's "Nova ordem paper" needs `max_stop_distance_pct`
 * for the implied stop-distance-% hint) plus the wallet's current usage.
 */
export async function getRiskLimits(orgId: string, portfolioId: string): Promise<RiskLimits> {
  return apiFetch<RiskLimits>(`${portfoliosBase(orgId)}/${portfolioId}/risk/limits`);
}
