import { NextResponse } from "next/server";

import { isDayString } from "@/components/meme-tests/meme-tests-format";
import { isApiError } from "@/lib/api-error";
import { fetchMemeTestsCsv } from "@/lib/api/meme-tests";
import { resolveOrgContext } from "@/lib/api/org-context";
import { logger } from "@/lib/logger";

export const dynamic = "force-dynamic";

/**
 * `GET /[orgSlug]/meme/testes/export?day=&rule_set=` -- hands the browser the
 * CSV `routers/meme_tests.py` renders (UTF-8 with BOM, `;`, Brasília). The
 * API is internal and wants the session's bearer token, which a plain
 * `<a href>` to it could never carry; this handler runs behind
 * `clerkMiddleware` (its path deliberately does not end in `.csv` -- the
 * middleware matcher skips `.csv` URLs as static files), resolves the org
 * the same way every page does, and streams the API's own bytes and headers
 * through unchanged.
 */
export async function GET(request: Request, { params }: { params: Promise<{ orgSlug: string }> }) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) return new NextResponse("organização não encontrada", { status: 404 });

  const search = new URL(request.url).searchParams;
  const dayParam = search.get("day");
  const day = isDayString(dayParam) ? dayParam : undefined;
  const ruleSet = search.get("rule_set") ?? undefined;
  try {
    const upstream = await fetchMemeTestsCsv(membership.organization.id, { day, ruleSet });
    const headers = new Headers({ "cache-control": "no-store" });
    const contentType = upstream.headers.get("content-type");
    const disposition = upstream.headers.get("content-disposition");
    headers.set("content-type", contentType ?? "text/csv; charset=utf-8");
    headers.set("content-disposition", disposition ?? `attachment; filename="testes-meme-${day ?? "hoje"}.csv"`);
    return new NextResponse(await upstream.arrayBuffer(), { status: 200, headers });
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : error instanceof Error ? error.message : "erro desconhecido";
    logger.error("meme_tests_csv_export_failed", { error: reason });
    const status = isApiError(error) ? error.status : 502;
    return new NextResponse(`falha ao exportar o CSV: ${reason}`, { status, headers: { "content-type": "text/plain; charset=utf-8" } });
  }
}
