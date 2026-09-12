import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import { MemeCurveChart } from "@/components/meme/meme-curve-chart";
import { MemeFeaturesTable } from "@/components/meme/meme-features-table";
import { completionSignals, signalMarks } from "@/components/meme/meme-graduation-signals";
import { MemeSignalMarks } from "@/components/meme/meme-signal-marks";
import { memeSourceLabel, memeTokenStateLabel } from "@/components/meme/labels";
import { formatMemePct, formatSol } from "@/components/meme/meme-format";
import { SectionUnavailable } from "@/components/ui/section-unavailable";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS } from "@/lib/auto-refresh-interval";
import { isApiError } from "@/lib/api-error";
import { getMemeToken } from "@/lib/api/meme";
import type { MemeTokenDetail } from "@/lib/api/meme-types";
import { resolveOrgContext } from "@/lib/api/org-context";
import { logger } from "@/lib/logger";

export interface MemeTokenPageProps {
  params: Promise<{ orgSlug: string; mint: string }>;
}

type DetailLoad = { ok: true; data: MemeTokenDetail } | { ok: false; reason: string; notFound: boolean };

async function loadDetail(orgId: string, mint: string): Promise<DetailLoad> {
  try {
    return { ok: true, data: await getMemeToken(orgId, mint) };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    const notFoundError = isApiError(error) && error.status === 404;
    if (!notFoundError) logger.error("meme_token_detail_load_failed", { mint, error: reason });
    return { ok: false, reason, notFound: notFoundError };
  }
}

/** `/[orgSlug]/meme/[mint]` — one pump.fun token: identity, the four completion signals with their marks on the curve chart (T4.2d), the mcap series, and the per-minute feature series with honest null-with-reason cells. Read-only (T4.3). */
export default async function MemeTokenPage({ params }: MemeTokenPageProps) {
  const { orgSlug, mint } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const result = await loadDetail(membership.organization.id, mint);
  if (!result.ok && result.notFound) notFound();

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh intervalMs={DEFAULT_AUTO_REFRESH_INTERVAL_MS} />
      {!result.ok ? (
        <SectionUnavailable title="Token" reason={`falha ao carregar (${result.reason})`} />
      ) : (
        <TokenDetailBody data={result.data} mint={mint} />
      )}
    </div>
  );
}

function TokenDetailBody({ data, mint }: { data: MemeTokenDetail; mint: string }) {
  const { token, snapshots, features } = data;
  const chronological = [...snapshots].reverse();

  return (
    <>
      <div>
        <h1 className="text-xl font-semibold text-fg">{token.name ?? "(nome desconhecido)"}</h1>
        <p className="text-xs text-fg-muted">
          {token.symbol ?? "(símbolo desconhecido)"} · <span className="font-mono">{mint}</span> · {memeTokenStateLabel(token.state)}
        </p>
        <p className="mt-1 text-xs text-fg-subtle">Só monitoramento — sem execução.</p>
      </div>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-md border border-border p-3">
          <p className="text-xs uppercase tracking-wide text-fg-muted">Mcap (SOL)</p>
          <p className="text-lg font-semibold tabular-nums text-fg">{token.mcap_sol === null ? "sem dado" : formatSol(token.mcap_sol)}</p>
        </div>
        <div className="rounded-md border border-border p-3">
          <p className="text-xs uppercase tracking-wide text-fg-muted">Progresso da curva</p>
          <p className="text-lg font-semibold tabular-nums text-fg">
            {token.curve_progress_pct === null ? "sem dado" : formatMemePct(token.curve_progress_pct)}
          </p>
        </div>
        <div className="rounded-md border border-border p-3">
          <p className="text-xs uppercase tracking-wide text-fg-muted">Criador</p>
          <p className="break-all font-mono text-xs text-fg">{token.creator ?? "desconhecido"}</p>
        </div>
        <div className="rounded-md border border-border p-3">
          <p className="text-xs uppercase tracking-wide text-fg-muted">Última observação</p>
          {token.snapshot_observed_at ? (
            <>
              <BrasiliaInstant iso={token.snapshot_observed_at} className="text-sm text-fg" />
              <p className="text-[11px] text-fg-subtle">{token.snapshot_source ? memeSourceLabel(token.snapshot_source) : ""}</p>
            </>
          ) : (
            <p className="text-sm text-fg-subtle">sem observação ainda</p>
          )}
        </div>
      </section>

      <MemeSignalMarks token={token} />

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-fg">Mcap ao longo do tempo</h2>
        <MemeCurveChart snapshots={chronological} marks={signalMarks(completionSignals(token))} />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-fg">Features por minuto</h2>
        <MemeFeaturesTable features={features} />
      </section>
    </>
  );
}
