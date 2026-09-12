import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { BetRecord } from "@/components/meme-tests/bet-record";
import { SectionUnavailable } from "@/components/ui/section-unavailable";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS } from "@/lib/auto-refresh-interval";
import { isApiError } from "@/lib/api-error";
import { getMemeTestDetail } from "@/lib/api/meme-tests";
import type { MemeTestDetail } from "@/lib/api/meme-tests-types";
import { resolveOrgContext } from "@/lib/api/org-context";
import { logger } from "@/lib/logger";

export interface MemeBetPageProps {
  params: Promise<{ orgSlug: string; betId: string }>;
}

type DetailLoad = { ok: true; data: MemeTestDetail } | { ok: false; reason: string; notFound: boolean };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function loadDetail(orgId: string, betId: string): Promise<DetailLoad> {
  try {
    return { ok: true, data: await getMemeTestDetail(orgId, betId) };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    const missing = isApiError(error) && error.status === 404;
    if (!missing) logger.error("meme_bet_record_load_failed", { betId, error: reason });
    return { ok: false, reason, notFound: missing };
  }
}

/** `/[orgSlug]/meme/mesa/aposta/[betId]` (brief T4.13 §3): one bet's complete record with the curve between entry and exit. Read-only. */
export default async function MemeBetPage({ params }: MemeBetPageProps) {
  const { orgSlug, betId } = await params;
  if (!UUID.test(betId)) notFound();
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const result = await loadDetail(membership.organization.id, betId);
  if (!result.ok && result.notFound) notFound();

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh intervalMs={DEFAULT_AUTO_REFRESH_INTERVAL_MS} />
      {!result.ok ? <SectionUnavailable title="Ficha da aposta" reason={`falha ao carregar (${result.reason})`} /> : <BetRecord orgSlug={orgSlug} detail={result.data} />}
    </div>
  );
}
