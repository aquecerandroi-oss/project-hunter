"use client";

import { RefreshCw } from "lucide-react";
import { useState, useTransition } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { refreshReadiness } from "@/lib/api/system-actions";
import type { ReadyStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export interface ReadinessPanelProps {
  initial: ReadyStatus;
}

function StatusBadge({ ok, detail }: { ok: boolean; detail?: string | undefined }) {
  return (
    <Badge variant={ok ? "positive" : "negative"}>
      {ok ? "OK" : detail ? `Indisponível (${detail})` : "Indisponível"}
    </Badge>
  );
}

/**
 * `GET /ready` (apps/api/hunter_api/health.py) -- 200 only when Postgres and
 * Redis both answer in time, 503 with per-dependency detail otherwise. The
 * page itself revalidates every 15s (`export const revalidate = 15`); this
 * button re-runs the real check on demand rather than waiting for that.
 */
export function ReadinessPanel({ initial }: ReadinessPanelProps) {
  const [status, setStatus] = useState(initial);
  // Tracks the last `initial` this component actually reconciled against --
  // React's own documented "adjust state when a prop changes" pattern
  // (https://react.dev/learn/you-might-not-need-an-effect), setting state
  // during render rather than in a `useEffect` (which would fire one render
  // late and trigger a cascading-render lint error). `useState(initial)`
  // alone only ever reads `initial` at mount; `AutoRefresh` re-renders the
  // System page with a fresh `/ready` result every cycle, but this component
  // instance survives that re-render (its position in the tree hasn't
  // changed), so without this the panel kept showing whatever it read once
  // at mount forever -- Redis going down after the page first loaded never
  // reached the screen (H6). The manual "Atualizar" click's `setStatus`
  // below still wins whenever it resolves after the next render, since
  // whichever update was dispatched more recently is what ends up rendered.
  const [syncedInitial, setSyncedInitial] = useState(initial);
  if (initial !== syncedInitial) {
    setSyncedInitial(initial);
    setStatus(initial);
  }
  const [pending, startTransition] = useTransition();

  function handleRefresh(): void {
    startTransition(async () => {
      setStatus(await refreshReadiness());
    });
  }

  const allOk = status.database && status.redis;

  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Dependências</h2>
        <Button type="button" variant="ghost" size="sm" onClick={handleRefresh} disabled={pending}>
          <RefreshCw className={cn("size-4", pending && "animate-spin")} />
          Atualizar
        </Button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant={allOk ? "positive" : "negative"}>{allOk ? "Ready" : "Not Ready"}</Badge>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-fg-muted">Postgres</dt>
          <dd className="mt-1">
            <StatusBadge ok={status.database} detail={status.database_detail} />
          </dd>
        </div>
        <div>
          <dt className="text-fg-muted">Redis</dt>
          <dd className="mt-1">
            <StatusBadge ok={status.redis} detail={status.redis_detail} />
          </dd>
        </div>
      </dl>
    </section>
  );
}
