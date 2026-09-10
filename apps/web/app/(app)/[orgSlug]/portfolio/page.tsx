import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { OrdersTable, PositionsTable, TradesTable } from "@/components/portfolio/portfolio-activity-tables";
import { ManualOrderSection } from "@/components/portfolio/manual-order-section";
import { ManualOrdersTable } from "@/components/portfolio/manual-orders-table";
import { PortfolioEmpty } from "@/components/portfolio/portfolio-empty";
import { PortfolioEquityChart } from "@/components/portfolio/portfolio-equity-chart";
import { PortfolioError } from "@/components/portfolio/portfolio-error";
import { PortfolioHeader } from "@/components/portfolio/portfolio-header";
import { PortfolioProposalsEmpty } from "@/components/portfolio/portfolio-proposals-empty";
import { PortfolioResultCard } from "@/components/portfolio/portfolio-result-card";
import { PortfolioRiskCard } from "@/components/portfolio/portfolio-risk-card";
import { PORTFOLIO_STATUS_LABEL } from "@/components/portfolio/labels";
import { SectionUnavailable } from "@/components/ui/section-unavailable";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS } from "@/lib/auto-refresh-interval";
import { isApiError } from "@/lib/api-error";
import {
  getEquityCurve,
  getKillSwitch,
  getOrders,
  getPortfolioAnchor,
  getPortfolioSummary,
  getPositions,
  getRiskLimits,
  getTrades,
  listPortfolios,
} from "@/lib/api/portfolio";
import { listManualOrders } from "@/lib/api/manual-orders";
import type { ManualOrderListItem } from "@/lib/api/manual-orders-types";
import type {
  AsOfPage,
  EquityCurvePoint,
  KillSwitchDetail,
  OrderRow,
  PortfolioAnchor,
  PortfolioSummary,
  PortfolioTradeRow,
  PositionRow,
} from "@/lib/api/portfolio-types";
import { resolveOrgContext, roleAtLeast } from "@/lib/api/org-context";
import { logger } from "@/lib/logger";

export interface PortfolioPageProps {
  params: Promise<{ orgSlug: string }>;
}

// No realtime publisher for `rt:org:{org_id}:portfolio:{id}` exists yet
// (execution-worker, T3.4/T3.5, is not built) -- same fallback cadence as
// `/lab` and `/system`: `AutoRefresh` re-runs this Server Component's own
// fetches on an interval instead of subscribing to a channel nothing publishes on.
const ACTIVITY_LIMIT = 200;

interface PortfolioData {
  summary: PortfolioSummary;
  anchor: PortfolioAnchor;
  equityCurve: AsOfPage<EquityCurvePoint>;
  positions: AsOfPage<PositionRow>;
  orders: AsOfPage<OrderRow>;
  trades: AsOfPage<PortfolioTradeRow>;
  killSwitch: KillSwitchDetail;
}

type PortfolioLoad = { ok: true; data: PortfolioData } | { ok: false; reason: string };

/** Fetches, never constructs JSX (`lab/page.tsx`'s own `loadLab` convention: a try/catch around JSX cannot actually catch a rendering error). */
async function loadPortfolio(orgId: string, portfolioId: string): Promise<PortfolioLoad> {
  try {
    const [summary, anchor, equityCurve, positions, orders, trades, killSwitch] = await Promise.all([
      getPortfolioSummary(orgId, portfolioId),
      getPortfolioAnchor(orgId, portfolioId),
      getEquityCurve(orgId, portfolioId, { limit: ACTIVITY_LIMIT }),
      getPositions(orgId, portfolioId, { limit: ACTIVITY_LIMIT }),
      getOrders(orgId, portfolioId, { limit: ACTIVITY_LIMIT }),
      getTrades(orgId, portfolioId, { limit: ACTIVITY_LIMIT }),
      getKillSwitch(orgId, portfolioId),
    ]);
    return { ok: true, data: { summary, anchor, equityCurve, positions, orders, trades, killSwitch } };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("portfolio_page_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

function reasonOf(error: unknown): string {
  return isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
}

interface ManualOrdersData {
  maxStopDistancePct: string | null;
  items: ManualOrderListItem[];
  asOf: string;
}

type ManualOrdersLoad = { ok: true; data: ManualOrdersData } | { ok: false; reason: string };

/**
 * Loaded independently from `loadPortfolio` above (T3.72): a failure here
 * (the write path's `GET .../risk/limits`/`.../orders` land in parallel with
 * this task, `.claude/state/brief-T3.68-ordem-manual-api.md`) must never take
 * down the wallet's own already-working summary/positions/trades -- each
 * loader owns its own honest failure.
 */
async function loadManualOrdersSection(orgId: string, portfolioId: string): Promise<ManualOrdersLoad> {
  try {
    const [riskLimits, ordersPage] = await Promise.all([
      getRiskLimits(orgId, portfolioId),
      listManualOrders(orgId, portfolioId, { limit: ACTIVITY_LIMIT }),
    ]);
    return {
      ok: true,
      data: {
        maxStopDistancePct: riskLimits.preset.max_stop_distance_pct,
        items: ordersPage.items,
        // The list contract is a plain cursor page with no `as_of` of its
        // own (unlike `AsOfPage`'s reads) -- this is when the web server
        // itself queried it, shown with the same Brasília component as every
        // other "consultado em" on this screen.
        asOf: new Date().toISOString(),
      },
    };
  } catch (error) {
    const reason = reasonOf(error);
    logger.error("manual_orders_section_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/** `/[orgSlug]/portfolio` (docs/plans/M3.md T3.8b) -- the organization's principal paper wallet. */
export default async function PortfolioPage({ params }: PortfolioPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  let mainWallet;
  try {
    const page = await listPortfolios(membership.organization.id, { limit: 200 });
    // The principal wallet is the one, permanent `type = "paper" AND NOT is_arena`
    // row (`packages/core/hunter_core/db/models/portfolios.py`'s own partial
    // unique index) -- there is at most one per organization today.
    mainWallet = page.items.find((p) => p.type === "paper" && !p.is_arena) ?? null;
  } catch (error) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-xl font-semibold text-fg">Carteira</h1>
        <PortfolioError reason={reasonOf(error)} />
      </div>
    );
  }

  if (!mainWallet) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-xl font-semibold text-fg">Carteira</h1>
        <PortfolioEmpty />
      </div>
    );
  }

  const [result, manualOrders] = await Promise.all([
    loadPortfolio(membership.organization.id, mainWallet.id),
    loadManualOrdersSection(membership.organization.id, mainWallet.id),
  ]);

  const canTrade = roleAtLeast(membership.role, "TRADER");

  return (
    <div className="flex flex-col gap-4">
      <AutoRefresh intervalMs={DEFAULT_AUTO_REFRESH_INTERVAL_MS} />
      <h1 className="text-xl font-semibold text-fg">Carteira</h1>
      {!result.ok ? (
        <PortfolioError reason={result.reason} />
      ) : (
        <>
          <PortfolioHeader summary={result.data.summary} />
          <div className="grid gap-4 lg:grid-cols-2">
            <PortfolioResultCard summary={result.data.summary} anchor={result.data.anchor} />
            <PortfolioRiskCard riskState={result.data.summary.risk_state} killSwitch={result.data.killSwitch} />
          </div>
          <PortfolioEquityChart points={result.data.equityCurve.items} asOf={result.data.equityCurve.as_of} />
          <ManualOrderSection
            orgId={membership.organization.id}
            portfolioId={mainWallet.id}
            canTrade={canTrade}
            walletOpenReason={
              result.data.summary.status !== "active"
                ? `A carteira está ${PORTFOLIO_STATUS_LABEL[result.data.summary.status]} -- não aberta para novas ordens.`
                : null
            }
            killSwitchReason={
              result.data.killSwitch.blocks_entries
                ? `Kill switch bloqueando entradas${result.data.killSwitch.reason ? `: ${result.data.killSwitch.reason}` : "."}`
                : null
            }
            maxStopDistancePct={manualOrders.ok ? manualOrders.data.maxStopDistancePct : null}
          >
            {!manualOrders.ok ? (
              <SectionUnavailable title="Propostas" reason={manualOrders.reason} />
            ) : manualOrders.data.items.length > 0 ? (
              <ManualOrdersTable items={manualOrders.data.items} asOf={manualOrders.data.asOf} />
            ) : (
              <PortfolioProposalsEmpty asOf={manualOrders.data.asOf} />
            )}
          </ManualOrderSection>
          <PositionsTable items={result.data.positions.items} asOf={result.data.positions.as_of} />
          <OrdersTable items={result.data.orders.items} asOf={result.data.orders.as_of} />
          <TradesTable items={result.data.trades.items} asOf={result.data.trades.as_of} />
        </>
      )}
    </div>
  );
}
