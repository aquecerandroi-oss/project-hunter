import { UserButton } from "@clerk/nextjs";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { LiveStatus } from "@/components/system/live-status";
import { Separator } from "@/components/ui/separator";
import { getMarketStatus } from "@/lib/api/system";
import type { MarketStatusResponse, ReadyStatus } from "@/lib/api/types";
import { logger } from "@/lib/logger";
import { cn } from "@/lib/utils";

export interface TopbarProps {
  orgSlug: string;
  /** The real `/ready` result (lib/api/system.ts), fetched once per server render by the layout -- never polled client-side faster than the page itself re-renders. `null` when the check could not even be attempted (e.g. `API_URL` unset). */
  systemStatus: ReadyStatus | null;
  children?: ReactNode;
}

type DotState = "ok" | "degraded" | "down";

function dotState(status: ReadyStatus | null): DotState {
  if (!status) return "down";
  if (status.database && status.redis) return "ok";
  if (status.database || status.redis) return "degraded";
  return "down";
}

const DOT_CLASSES: Record<DotState, string> = {
  ok: "bg-green",
  degraded: "bg-warning",
  down: "bg-red",
};

const DOT_LABELS: Record<DotState, string> = {
  ok: "Sistema operacional",
  degraded: "Sistema degradado",
  down: "Sistema indisponível",
};

/** Small ponto verde/âmbar/vermelho (docs/DESIGN.md §3), title-tooltipped and announced to screen readers. */
function SystemStatusDot({ status }: { status: ReadyStatus | null }) {
  const state = dotState(status);
  return (
    <span className="inline-flex items-center" title={DOT_LABELS[state]}>
      <span className={cn("size-2 rounded-full", DOT_CLASSES[state])} aria-hidden="true" />
      <span className="sr-only">{DOT_LABELS[state]}</span>
    </span>
  );
}

/** `/system/market-status` (T1.4) can 404/500 before that piece deploys -- the topbar must never 500 the whole shell over a missing widget. */
async function marketStatusOrNull(): Promise<MarketStatusResponse | null> {
  try {
    return await getMarketStatus();
  } catch (error) {
    logger.error("topbar_market_status_load_failed", { error: error instanceof Error ? error.message : String(error) });
    return null;
  }
}

export async function Topbar({ orgSlug, systemStatus, children }: TopbarProps) {
  const marketStatus = await marketStatusOrNull();
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-bg-elevated px-4">
      {children}
      {/*
       * A subtle gold glow is one of the two places docs/DESIGN.md §2
       * allows it (the other is the dashboard header) -- kept to a small
       * text-shadow, never a background gradient.
       */}
      <span
        className="shrink-0 text-sm font-bold tracking-wide text-gold"
        style={{ textShadow: "0 0 12px color-mix(in srgb, var(--color-gold) 45%, transparent)" }}
      >
        HUNTER
      </span>
      <Separator orientation="vertical" className="h-5" />
      {/*
       * TODO(T09): docs/PRODUCT.md notes a user can belong to several
       * organizations ("Um usuário pode pertencer a várias organizações").
       * Once multi-org UI lands, this plain org-slug label becomes an org
       * switcher (dropdown across the user's orgs). Not built here -- out
       * of scope for this task.
       */}
      <span className="truncate text-sm font-medium text-fg-muted">{orgSlug}</span>
      <SystemStatusDot status={systemStatus} />
      <Separator orientation="vertical" className="h-5" />
      {marketStatus ? (
        <LiveStatus variant="compact" initial={marketStatus} />
      ) : (
        <span className="text-xs text-fg-subtle" title="Mercados: status indisponível no momento">
          mercados indisponível
        </span>
      )}
      <div className="ml-auto flex items-center gap-2">
        <ThemeToggle />
        <Separator orientation="vertical" className="h-6" />
        <UserButton />
      </div>
    </header>
  );
}
