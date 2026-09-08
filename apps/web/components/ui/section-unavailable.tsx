"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export interface SectionUnavailableProps {
  title: string;
  reason: string;
}

/**
 * Shared honest-failure box for a page section (T3.24a's brief §2, fixes
 * S2/X2): same shape as `radar-error.tsx`/`lab-error.tsx`'s full-page
 * version, sized for sitting alongside other cards on `/system` instead of
 * taking the whole viewport. `router.refresh()` re-runs the page's own
 * server fetch -- there is no separate retry endpoint to call.
 */
export function SectionUnavailable({ title, reason }: SectionUnavailableProps) {
  const router = useRouter();
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
