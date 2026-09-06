import { notFound } from "next/navigation";

import { RadarError } from "@/components/radar/radar-error";
import { RadarFilters, type RadarFiltersState } from "@/components/radar/radar-filters";
import { RadarTable } from "@/components/radar/radar-table";
import { isApiError } from "@/lib/api-error";
import { listAnomalies } from "@/lib/api/anomalies";
import { MAX_ANOMALY_WINDOW_HOURS, buildAnomaliesAggregate, unavailableAnomaliesAggregate } from "@/lib/api/anomalies-types";
import type { AnomaliesAggregate } from "@/lib/api/anomalies-types";
import { resolveOrgContext } from "@/lib/api/org-context";
import { listRadar } from "@/lib/api/radar";
import type {
  AnomalyTypeValue,
  MarketRegimeValue,
  OpportunityStage,
  RadarPage as RadarPageData,
  RadarParams,
  RadarSortKey,
  RadarSortOrder,
  RadarStatusFilter,
} from "@/lib/api/radar-types";
import { logger } from "@/lib/logger";

export interface RadarPageProps {
  params: Promise<{ orgSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

// Matches `/markets`/`/lab`'s convention: one request at the API's own max
// page size, which doubles as this table's virtualization/realtime budget.
const RADAR_PAGE_LIMIT = 200;
const SORT_KEYS: RadarSortKey[] = ["score", "change", "volume", "age"];

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function many<T extends string>(value: string | string[] | undefined): T[] {
  if (value === undefined) return [];
  return (Array.isArray(value) ? value : [value]) as T[];
}

function parseFilters(sp: Record<string, string | string[] | undefined>): {
  filters: RadarFiltersState;
  sort: RadarSortKey;
  order: RadarSortOrder;
} {
  const sortRaw = first(sp.sort);
  const sort = SORT_KEYS.includes(sortRaw as RadarSortKey) ? (sortRaw as RadarSortKey) : "score";
  const order: RadarSortOrder = first(sp.order) === "asc" ? "asc" : "desc";
  return {
    filters: {
      q: first(sp.q),
      scoreMin: first(sp.score_min),
      status: many<RadarStatusFilter>(sp.status),
      stage: many<OpportunityStage>(sp.stage),
      exchange: first(sp.exchange),
      anomalyType: first(sp.anomaly_type) as AnomalyTypeValue | "",
      regime: first(sp.regime) as MarketRegimeValue | "",
      volatilityMin: first(sp.volatility_min),
      volatilityMax: first(sp.volatility_max),
    },
    sort,
    order,
  };
}

function toRadarParams(filters: RadarFiltersState, sort: RadarSortKey, order: RadarSortOrder, orgId: string): RadarParams {
  const params: RadarParams = { org_id: orgId, sort, order, limit: RADAR_PAGE_LIMIT };
  if (filters.q) params.q = filters.q;
  if (filters.scoreMin) params.score_min = filters.scoreMin;
  if (filters.status.length) params.status = filters.status;
  if (filters.stage.length) params.stage = filters.stage;
  if (filters.exchange) params.exchange = filters.exchange;
  if (filters.anomalyType) params.anomaly_type = filters.anomalyType;
  if (filters.regime) params.regime = filters.regime;
  if (filters.volatilityMin) params.volatility_min = filters.volatilityMin;
  if (filters.volatilityMax) params.volatility_max = filters.volatilityMax;
  return params;
}

type RadarLoad = { ok: true; page: RadarPageData } | { ok: false; reason: string };

async function loadRadarPage(params: RadarParams): Promise<RadarLoad> {
  try {
    const page = await listRadar(params);
    return { ok: true, page };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("radar_page_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/**
 * One global "active, last 30 days" anomalies read, grouped by `market_id`,
 * feeding the radar table's "anomalias ativas" column. Deliberately NOT one
 * request per row (would not scale to 200 rows) and deliberately labelled
 * with its own scope AND its own `as_of` everywhere it is rendered (Astra's
 * T2.7 review, must-fix 2 and 3) -- see `components/radar/anomaly-count-cell.tsx`.
 * `hooks/useRadarPage.ts` refetches this same aggregate (via
 * `lib/api/anomalies-actions.ts::loadRadarAnomaliesAggregateAction`, which
 * shares `buildAnomaliesAggregate` with this function) on every
 * reconciliation, so it never sits frozen at its initial SSR value while the
 * radar rows keep refreshing.
 */
async function loadAnomaliesAggregate(): Promise<AnomaliesAggregate> {
  try {
    const page = await listAnomalies({ status: "active", window_hours: MAX_ANOMALY_WINDOW_HOURS, limit: 200 });
    return buildAnomaliesAggregate(page);
  } catch (error) {
    logger.error("radar_anomalies_aggregate_failed", { error: error instanceof Error ? error.message : String(error) });
    return unavailableAnomaliesAggregate();
  }
}

/** `/[orgSlug]/radar` (docs/plans/M2.md T2.7) -- the cross-market opportunity radar. */
export default async function RadarPage({ params, searchParams }: RadarPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const sp = await searchParams;
  const { filters, sort, order } = parseFilters(sp);
  const radarParams = toRadarParams(filters, sort, order, membership.organization.id);

  const [radarLoad, anomaliesAggregate] = await Promise.all([loadRadarPage(radarParams), loadAnomaliesAggregate()]);

  const hasFilters =
    filters.q !== "" ||
    filters.scoreMin !== "" ||
    filters.status.length > 0 ||
    filters.stage.length > 0 ||
    filters.exchange !== "" ||
    filters.anomalyType !== "" ||
    filters.regime !== "" ||
    filters.volatilityMin !== "" ||
    filters.volatilityMax !== "";

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-fg">Radar</h1>
      <RadarFilters state={filters} hasOrg />
      {!radarLoad.ok ? (
        <RadarError reason={radarLoad.reason} />
      ) : (
        <RadarTable
          orgSlug={orgSlug}
          initialItems={radarLoad.page.items}
          initialCursor={radarLoad.page.next_cursor ?? null}
          initialAsOf={radarLoad.page.as_of}
          hasFilters={hasFilters}
          baseParams={radarParams}
          initialAnomalies={anomaliesAggregate}
        />
      )}
    </div>
  );
}
