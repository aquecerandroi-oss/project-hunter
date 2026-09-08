"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export interface SectionUnavailableProps {
  title: string;
  reason: string;
  /**
   * Inline, low-profile rendering for a tight header/topbar slot (T3.28b:
   * the topbar's market-status widget used to swallow its own fetch
   * failure into a plain, retry-less span instead of this shared
   * honest-failure treatment). Same message + retry as the default bordered
   * box, without the padding/border that only fits a card-sized area.
   */
  compact?: boolean;
}

/**
 * Shared honest-failure box for a page section (T3.24a's brief §2, fixes
 * S2/X2): same shape as `radar-error.tsx`/`lab-error.tsx`'s full-page
 * version, sized for sitting alongside other cards on `/system` instead of
 * taking the whole viewport. `router.refresh()` re-runs the page's own
 * server fetch -- there is no separate retry endpoint to call.
 */
export function SectionUnavailable({ title, reason, compact = false }: SectionUnavailableProps) {
  const router = useRouter();

  if (compact) {
    return (
      <span className="inline-flex min-w-0 items-center gap-1.5 text-xs text-fg-muted" title={`${title} indisponível: ${reason}`}>
        <span className="truncate">
          {title} indisponível: {reason}
        </span>
        <button
          type="button"
          onClick={() => router.refresh()}
          className="shrink-0 rounded-sm text-fg-muted underline decoration-dotted underline-offset-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
        >
          Tentar de novo
        </button>
      </span>
    );
  }

  return (
    <div className="rounded-lg border border-dashed border-red/40 bg-bg-elevated p-4">
      <p className="text-sm text-fg">
        {title} indisponível: {reason}
      </p>
      <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => router.refresh()}>
        Tentar novamente
      </Button>
    </div>
  );
}
