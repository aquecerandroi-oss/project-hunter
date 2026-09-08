"use client";

import { Button } from "@/components/ui/button";

export interface LabLoadMoreProps {
  cursor: string | null;
  loadingMore: boolean;
  loadError: string | null;
  onLoadMore: () => void;
}

/** The "Carregar mais"/"Fim da lista" control + its own error line -- split out of `LabSignalsTable` so that function's own cyclomatic complexity stays under the lint config's budget. */
export function LabLoadMore({ cursor, loadingMore, loadError, onLoadMore }: LabLoadMoreProps) {
  const label = cursor ? (loadingMore ? "Carregando..." : "Carregar mais") : "Fim da lista";
  return (
    <div className="flex items-center gap-2">
      <Button type="button" variant="outline" size="sm" onClick={onLoadMore} disabled={!cursor || loadingMore}>
        {label}
      </Button>
      {loadError && <span className="text-xs text-red">{loadError}</span>}
    </div>
  );
}
