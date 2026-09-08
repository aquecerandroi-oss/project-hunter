import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { LabCurveSection } from "@/components/lab/lab-curve-section";
import { LabError } from "@/components/lab/lab-error";
import { LabFilters } from "@/components/lab/lab-filters";
import { LabHeader } from "@/components/lab/lab-header";
import { buildReferenceRuler, buildWalletRuler, type MoneyRuler } from "@/components/lab/lab-money";
import { LabScoreboardSection } from "@/components/lab/lab-scoreboard-section";
import { LabSignalsTable } from "@/components/lab/lab-signals-table";
import { LabTabs } from "@/components/lab/lab-tabs";
import { LabVersionCard } from "@/components/lab/lab-version-card";
import { LabVersionsEmpty } from "@/components/lab/lab-versions-empty";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS } from "@/lib/auto-refresh-interval";
import { isApiError } from "@/lib/api-error";
import { getLabCurve, getLabScoreboard, getLabSignals, getLabSummary, listLabVersions } from "@/lib/api/lab";
import type { LabSignalsParams } from "@/lib/api/lab";
import type { CurveOut, LabSignalsPage, LabSummaryOut, LabVersionsOut, ScoreboardOut, ScoreboardRowOut } from "@/lib/api/lab-types";
import { resolveOrgContext } from "@/lib/api/org-context";
import { getPortfolioSummary, listPortfolios } from "@/lib/api/portfolio";
import { logger } from "@/lib/logger";

export interface LabPageProps {
  params: Promise<{ orgSlug: string }>;
  searchParams: Promise<{ window?: string; cohort?: string; version?: string }>;
}

// No realtime channel and no per-response `stale_after_ms` of its own (this
// is a research endpoint, not live market data) -- same fallback cadence
// `system/page.tsx` uses, plus `AutoRefresh` for an already-open tab
// (T1.5 review F2's fix, reused here).
export const revalidate = 15;

// Signals list is fetched once per page load at the API's own max page size
// (`MAX_PAGE_SIZE = 200`, `repositories/base.py`) so the virtualized table
// starts with a real >= 200-row budget, exactly like `/markets` (T1.5 M1).
const SIGNALS_INITIAL_LIMIT = 200;

const WINDOWS = ["7d", "30d", "all"] as const;
type LabWindow = (typeof WINDOWS)[number];

function isWindow(value: string | undefined): value is LabWindow {
  return WINDOWS.includes(value as LabWindow);
}

type LabLoad =
  | { ok: true; summary: LabSummaryOut; versions: LabVersionsOut; signals: LabSignalsPage }
  | { ok: false; reason: string };

/**
 * Fetches, never constructs JSX (same split as `markets/page.tsx`'s
 * `loadMarkets`: a try/catch around JSX can't actually catch a rendering
 * error, since React doesn't render synchronously inside it).
 */
async function loadLab(window: LabWindow, cohort: string, versionId: string | undefined): Promise<LabLoad> {
  try {
    const signalsParams: LabSignalsParams = { cohort, limit: SIGNALS_INITIAL_LIMIT };
    if (versionId) signalsParams.strategy_version_id = versionId;
    const [summary, versions, signals] = await Promise.all([
      getLabSummary({ window, cohort }),
      listLabVersions(),
      getLabSignals(signalsParams),
    ]);
    return { ok: true, summary, versions, signals };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("lab_page_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

type ScoreboardLoad =
  | { ok: true; scoreboard: ScoreboardOut; curvesById: Record<string, CurveOut | null> }
  | { ok: false; reason: string };

/**
 * One `/curve` call per version (brief T3.18 item 4), all in parallel, keyed
 * by `version_id`. A single version's curve failing never fails the whole
 * Placar -- its line is simply absent (`LabCurveChart`/`buildCurveSeries`
 * read a missing/`null` entry as "failed", never a fabricated flat line).
 */
async function loadCurves(rows: ScoreboardRowOut[], asOf: string): Promise<Record<string, CurveOut | null>> {
  const settled = await Promise.allSettled(rows.map((row) => getLabCurve({ version_id: row.version.id, as_of: asOf })));
  const curvesById: Record<string, CurveOut | null> = {};
  rows.forEach((row, index) => {
    const result = settled[index];
    if (result?.status === "fulfilled") {
      curvesById[row.version.id] = result.value;
    } else {
      logger.error("lab_curve_load_failed", { versionId: row.version.id, error: String(result?.reason) });
      curvesById[row.version.id] = null;
    }
  });
  return curvesById;
}

/**
 * The Placar's own data (brief T3.18 items 1-2): a single frozen `as_of`
 * shared by the scoreboard call and every per-version curve call, so the
 * curve lines are guaranteed to reflect the exact same population the cards
 * summarize -- never two snapshots a few milliseconds apart. Independent of
 * `loadLab`: a Placar failure degrades to its own inline message instead of
 * blocking the rest of the page (same philosophy as `loadMoneyRuler`).
 */
async function loadScoreboard(): Promise<ScoreboardLoad> {
  try {
    const asOf = new Date().toISOString();
    const scoreboard = await getLabScoreboard({ as_of: asOf });
    const curvesById = await loadCurves(scoreboard.rows, asOf);
    return { ok: true, scoreboard, curvesById };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("lab_scoreboard_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/**
 * The organization's real principal paper wallet equity (brief T3.17: "a
 * quantia do patrimônio, nunca digitada"), or a fixed, labelled reference
 * when there is none yet -- mirrors `portfolio/page.tsx`'s own `type =
 * "paper" && !is_arena` lookup. Never throws: any failure (no wallet, no
 * session, API down) degrades to the honest reference ruler rather than
 * failing the whole Lab page over a display-only enhancement.
 */
async function loadMoneyRuler(orgId: string): Promise<MoneyRuler> {
  try {
    const page = await listPortfolios(orgId, { limit: 200 });
    const mainWallet = page.items.find((p) => p.type === "paper" && !p.is_arena) ?? null;
    if (!mainWallet) return buildReferenceRuler();
    const summary = await getPortfolioSummary(orgId, mainWallet.id);
    return buildWalletRuler(summary.equity, summary.brl?.equity_brl ?? null);
  } catch (error) {
    logger.error("lab_money_ruler_load_failed", { error: String(error) });
    return buildReferenceRuler();
  }
}

/** `/[orgSlug]/lab` (docs/plans/SHADOW-LAB.md, S3): the Shadow tab -- hypothetical, no-capital decisions and their tracked outcomes over real M1 data. */
export default async function LabPage({ params, searchParams }: LabPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const sp = await searchParams;
  const window: LabWindow = isWindow(sp.window) ? sp.window : "30d";
  const cohort = sp.cohort?.trim() || "prospective";
  const versionId = sp.version || undefined;

  const [result, ruler, scoreboardResult] = await Promise.all([
    loadLab(window, cohort, versionId),
    loadMoneyRuler(membership.organization.id),
    loadScoreboard(),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <AutoRefresh intervalMs={DEFAULT_AUTO_REFRESH_INTERVAL_MS} />
      <h1 className="text-xl font-semibold text-fg">Lab</h1>

      {/* The Placar (brief T3.18, "top of /lab"): every version that has ever
          emitted a signal, at a glance -- independent of the window/cohort
          filters below (the scoreboard API only accepts `as_of`, which this
          page freezes at load time, never a rolling window). */}
      <section className="flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold text-fg">Placar</h2>
          <p className="text-xs text-fg-muted">
            Uma linha por versão que já emitiu sinal, ordenada por status ativo primeiro e depois pelo resultado acumulado (R).
          </p>
        </div>
        {scoreboardResult.ok ? (
          <>
            <LabScoreboardSection rows={scoreboardResult.scoreboard.rows} ruler={ruler} />
            <LabCurveSection rows={scoreboardResult.scoreboard.rows} curvesById={scoreboardResult.curvesById} ruler={ruler} />
          </>
        ) : (
          <p className="text-sm text-red">Placar indisponível: falha ao carregar ({scoreboardResult.reason}).</p>
        )}
      </section>

      <LabTabs />
      {!result.ok ? (
        <LabError reason={result.reason} />
      ) : (
        <LabPageBody orgSlug={orgSlug} window={window} cohort={cohort} versionId={versionId} ruler={ruler} {...result} />
      )}
    </div>
  );
}

interface LabPageBodyProps {
  orgSlug: string;
  window: LabWindow;
  cohort: string;
  versionId: string | undefined;
  ruler: MoneyRuler;
  summary: LabSummaryOut;
  versions: LabVersionsOut;
  signals: LabSignalsPage;
}

function LabPageBody({ orgSlug, window, cohort, versionId, ruler, summary, versions, signals }: LabPageBodyProps) {
  const versionLabelById: Record<string, string> = {};
  for (const v of versions.items) versionLabelById[v.strategy_version_id] = `${v.strategy_key}/${v.version}`;
  for (const v of summary.versions) versionLabelById[v.strategy_version_id] ??= `${v.strategy_key}/${v.version}`;

  // `superseded_by` only exists on the `/versions` catalogue item (best-effort,
  // regex-reconstructed from `changelog` -- contract-S3-lab.md), not on the
  // `/summary` item; resolved to a label only when the target is also
  // rendered on this page (so the `#version-<id>` anchor always has a match).
  const catalogueById = new Map(versions.items.map((v) => [v.strategy_version_id, v]));

  const filterVersionOptions = summary.versions.map((v) => ({
    id: v.strategy_version_id,
    label: `${v.strategy_key}/${v.version} (${v.status})`,
  }));

  return (
    <>
      <LabHeader asOf={summary.as_of} versions={summary.versions} ruler={ruler} />
      <LabFilters window={window} cohort={cohort} versionId={versionId ?? null} versions={filterVersionOptions} />

      <section className="flex flex-col gap-4">
        {summary.versions.length === 0 ? (
          <LabVersionsEmpty />
        ) : (
          summary.versions.map((v) => {
            const supersededById = catalogueById.get(v.strategy_version_id)?.superseded_by ?? null;
            const supersededBy =
              supersededById && versionLabelById[supersededById]
                ? { id: supersededById, label: versionLabelById[supersededById] }
                : null;
            return <LabVersionCard key={v.strategy_version_id} version={v} supersededBy={supersededBy} />;
          })
        )}
      </section>

      <LabSignalsTable
        orgSlug={orgSlug}
        initialItems={signals.items}
        initialCursor={signals.next_cursor}
        baseParams={{ cohort, limit: SIGNALS_INITIAL_LIMIT, ...(versionId ? { strategy_version_id: versionId } : {}) }}
        versionLabelById={versionLabelById}
        cohort={cohort}
        ruler={ruler}
      />
    </>
  );
}
