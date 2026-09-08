import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { LabCurveSection } from "@/components/lab/lab-curve-section";
import { LabError } from "@/components/lab/lab-error";
import { LabHeader } from "@/components/lab/lab-header";
import { buildReferenceRuler, buildWalletRuler, type MoneyRuler } from "@/components/lab/lab-money";
import { LabPageBody, type LabSignalsLoad } from "@/components/lab/lab-page-body";
import { LabScoreboardSection } from "@/components/lab/lab-scoreboard-section";
import { parseLabSignalsQuery, type LabSignalsRawSearchParams } from "@/components/lab/lab-signals-search-params";
import { SectionUnavailable } from "@/components/ui/section-unavailable";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS } from "@/lib/auto-refresh-interval";
import { isApiError } from "@/lib/api-error";
import { getLabCurve, getLabScoreboard, getLabSignals, getLabSummary, listLabVersions } from "@/lib/api/lab";
import type { CurveOut, LabSignalsPageSize, LabSignalsState, LabSummaryOut, LabVersionsOut, ScoreboardOut, ScoreboardRowOut } from "@/lib/api/lab-types";
import { resolveOrgContext } from "@/lib/api/org-context";
import { getPortfolioSummary, listPortfolios } from "@/lib/api/portfolio";
import { logger } from "@/lib/logger";

export interface LabPageProps {
  params: Promise<{ orgSlug: string }>;
  searchParams: Promise<{ window?: string; cohort?: string; version?: string } & LabSignalsRawSearchParams>;
}

// No realtime channel and no per-response `stale_after_ms` of its own (this
// is a research endpoint, not live market data) -- same fallback cadence
// `system/page.tsx` uses, plus `AutoRefresh` for an already-open tab
// (T1.5 review F2's fix, reused here).
export const revalidate = 15;

const WINDOWS = ["7d", "30d", "all"] as const;
type LabWindow = (typeof WINDOWS)[number];

function isWindow(value: string | undefined): value is LabWindow {
  return WINDOWS.includes(value as LabWindow);
}

type LabLoad = { ok: true; summary: LabSummaryOut; versions: LabVersionsOut } | { ok: false; reason: string };

/**
 * Summary + the frozen versions catalogue -- independent of the signals list
 * since T3.37 (its own `loadSignals` below can fail on its own, isolated,
 * `SectionUnavailable`-scoped failure instead of taking the header/versions
 * down with it).
 */
async function loadLab(window: LabWindow, cohort: string): Promise<LabLoad> {
  try {
    const [summary, versions] = await Promise.all([getLabSummary({ window, cohort }), listLabVersions()]);
    return { ok: true, summary, versions };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("lab_page_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

interface LoadSignalsParams {
  cohort: string;
  versionId: string | undefined;
  state: LabSignalsState;
  pageSize: LabSignalsPageSize;
  cursor: string | undefined;
}

/**
 * The signals list on its own (T3.37): `state`/`page_size`/`cursor` come
 * straight from the URL (the segment tabs and the pager both rewrite it and
 * let this Server Component refetch -- `lab-signals-query.ts`'s
 * `buildLabHref`), so a failure here degrades to `SectionUnavailable` for
 * just "Sinais — Sombra" instead of the whole page (mirrors `loadScoreboard`
 * below).
 */
async function loadSignals({ cohort, versionId, state, pageSize, cursor }: LoadSignalsParams): Promise<LabSignalsLoad> {
  try {
    const page = await getLabSignals({
      cohort,
      state,
      page_size: pageSize,
      ...(cursor !== undefined ? { cursor } : {}),
      ...(versionId ? { strategy_version_id: versionId } : {}),
    });
    return { ok: true, page };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("lab_signals_load_failed", { error: reason });
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

function Eyebrow({ children }: { children: string }) {
  return <p className="text-xs font-medium uppercase tracking-wide text-fg-muted">{children}</p>;
}

/**
 * `/[orgSlug]/lab` (docs/plans/SHADOW-LAB.md, S3): the Shadow tab --
 * hypothetical, no-capital decisions and their tracked outcomes over real M1
 * data. Page order per brief T3.24b (opção A, "Placar-primeiro"): faixa
 * SOMBRA -> Placar -> Sinais — Sombra -> Versões (pesquisa) -- the SOMBRA
 * banner moved above the Placar and now renders even when `loadLab` itself
 * fails (its own ruler/costs come from independent, always-degrading loads).
 */
export default async function LabPage({ params, searchParams }: LabPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const sp = await searchParams;
  const window: LabWindow = isWindow(sp.window) ? sp.window : "30d";
  const cohort = sp.cohort?.trim() || "prospective";
  const versionId = sp.version || undefined;
  const { state, pageSize, cursorPath, cursor } = parseLabSignalsQuery(sp);

  const [result, ruler, scoreboardResult, signalsResult] = await Promise.all([
    loadLab(window, cohort),
    loadMoneyRuler(membership.organization.id),
    loadScoreboard(),
    loadSignals({ cohort, versionId, state, pageSize, cursor }),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh intervalMs={DEFAULT_AUTO_REFRESH_INTERVAL_MS} />
      <h1 className="text-xl font-semibold text-fg">Lab</h1>

      <LabHeader asOf={result.ok ? result.summary.as_of : null} versions={result.ok ? result.summary.versions : []} ruler={ruler} />

      {/* The Placar (brief T3.18, opção A: "top of /lab" right after the
          SOMBRA banner): every version that has ever emitted a signal, at a
          glance -- independent of the window/cohort filters below (the
          scoreboard API only accepts `as_of`, which this page freezes at
          load time, never a rolling window). */}
      <section className="flex flex-col gap-4">
        <div>
          <Eyebrow>Placar</Eyebrow>
          <p className="text-xs text-fg-muted">
            Uma linha por versão que já emitiu sinal, ordenada por status ativo primeiro e depois pelo resultado acumulado (R).
          </p>
        </div>
        {scoreboardResult.ok ? (
          <>
            <LabScoreboardSection rows={scoreboardResult.scoreboard.rows} ruler={ruler} />
            <LabCurveSection
              rows={scoreboardResult.scoreboard.rows}
              curvesById={scoreboardResult.curvesById}
              ruler={ruler}
              asOf={scoreboardResult.scoreboard.as_of}
            />
          </>
        ) : (
          <SectionUnavailable title="Placar" reason={`falha ao carregar (${scoreboardResult.reason})`} />
        )}
      </section>

      {!result.ok ? (
        <LabError reason={result.reason} />
      ) : (
        <LabPageBody
          orgSlug={orgSlug}
          window={window}
          cohort={cohort}
          versionId={versionId}
          state={state}
          pageSize={pageSize}
          cursorPath={cursorPath}
          ruler={ruler}
          summary={result.summary}
          versions={result.versions}
          signalsResult={signalsResult}
        />
      )}
    </div>
  );
}
