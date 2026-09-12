"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useRowHeight } from "@/hooks/useDensity";
import { useVirtualizedRows } from "@/hooks/useVirtualizedRows";
import { loadMemeTokensAction } from "@/lib/api/meme-actions";
import type { ListMemeTokensParams } from "@/lib/api/meme";
import type { MemeToken } from "@/lib/api/meme-types";
import { logger } from "@/lib/logger";

import { MemeTokenRow } from "./meme-token-row";

export interface MemeTokensTableProps {
  orgId: string;
  orgSlug: string;
  initialItems: MemeToken[];
  initialCursor: string | null;
  baseParams: ListMemeTokensParams;
}

const OVERSCAN = 8;
const VIEWPORT_HEIGHT = 480;
const HEADERS = ["Token", "Idade", "Mcap (SOL)", "Progresso", "Estado", "Criador", "Última observação"];

/** Virtualized per CLAUDE.md's "tables virtualize at >= 200 rows" -- the radar's tracked universe starts small but has no fixed ceiling (docs/plans/T4-MEME-RADAR.md, tens of thousands of tokens created per day). Sorting/filtering are server-driven (`?sort=`/`?state=` on the page itself, `meme/page.tsx`); this component only owns the virtualized viewport and "carregar mais". */
export function MemeTokensTable({ orgId, orgSlug, initialItems, initialCursor, baseParams }: MemeTokensTableProps) {
  const rowHeight = useRowHeight();
  const [items, setItems] = useState(initialItems);
  const [cursor, setCursor] = useState(initialCursor);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const requestIdRef = useRef(0);

  useEffect(() => {
    // A new filter/sort navigation on `meme/page.tsx` passes genuinely new
    // `initialItems`/`initialCursor` -- resync instead of only seeding the
    // initial `useState` (same fix `OpportunitiesTable` needed, T2.7 review).
    requestIdRef.current += 1;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resyncing from a new server-provided page (filters/sort changed)
    setItems(initialItems);
    setCursor(initialCursor);
  }, [initialItems, initialCursor]);

  const { visibleRows, topPad, bottomPad } = useVirtualizedRows({
    rows: items,
    rowHeight,
    scrollTop,
    viewportHeight: VIEWPORT_HEIGHT,
    overscan: OVERSCAN,
  });

  async function loadMore(): Promise<void> {
    if (!cursor || loadingMore) return;
    const myRequestId = ++requestIdRef.current;
    setLoadingMore(true);
    setLoadError(null);
    try {
      const outcome = await loadMemeTokensAction(orgId, { ...baseParams, cursor });
      if (requestIdRef.current !== myRequestId) return;
      if (!outcome.ok) {
        setLoadError(outcome.reason ?? "erro desconhecido");
        return;
      }
      setItems((prev) => [...prev, ...outcome.page.items]);
      setCursor(outcome.page.next_cursor ?? null);
    } catch (error) {
      logger.error("meme_tokens_load_more_failed", { error: String(error) });
      if (requestIdRef.current === myRequestId) setLoadError("falha ao carregar mais tokens");
    } finally {
      if (requestIdRef.current === myRequestId) setLoadingMore(false);
    }
  }

  if (items.length === 0) {
    return <p className="rounded-md border border-border p-4 text-sm text-fg-muted">Nenhum token no radar ainda para este filtro.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto rounded-md border border-border">
        <div onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)} style={{ height: VIEWPORT_HEIGHT, overflowY: "auto" }}>
          <table className="w-full text-left text-[13px]">
            <thead className="sticky top-0 bg-bg-elevated text-[11px] uppercase tracking-wide text-fg-muted">
              <tr>
                {HEADERS.map((h, i) => (
                  <th key={h} className={`px-3 py-2 ${i >= 4 ? "hidden md:table-cell" : ""} ${i >= 1 ? "text-right" : ""}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topPad > 0 && (
                <tr aria-hidden="true" style={{ height: topPad }}>
                  <td colSpan={HEADERS.length} />
                </tr>
              )}
              {visibleRows.map((row) => (
                <MemeTokenRow key={row.mint} orgSlug={orgSlug} row={row} rowHeight={rowHeight} />
              ))}
              {bottomPad > 0 && (
                <tr aria-hidden="true" style={{ height: bottomPad }}>
                  <td colSpan={HEADERS.length} />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => void loadMore()} disabled={!cursor || loadingMore}>
          {cursor ? (loadingMore ? "Carregando..." : "Carregar mais") : "Fim da lista"}
        </Button>
        {loadError && <span className="text-xs text-red">{loadError}</span>}
      </div>
    </div>
  );
}
