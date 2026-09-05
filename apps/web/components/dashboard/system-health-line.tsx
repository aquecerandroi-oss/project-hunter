import Link from "next/link";

import { dotState, DOT_CLASSES, DOT_LABELS } from "@/components/layout/topbar";
import type { ReadyStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export interface SystemHealthLineProps {
  orgSlug: string;
  /** `null` when the check itself could not be attempted -- reuses `topbar.tsx`'s `dotState`, so "sem verificação" and a real "indisponível" are never conflated (T1.5b joint decision #5). */
  status: ReadyStatus | null;
}

/**
 * The dashboard's one-line health summary (joint decision #2: diagnosis
 * detail lives in System, the dashboard only needs a single honest line).
 * Links to `/system` for the full readiness/workers breakdown instead of
 * duplicating it here.
 */
export function SystemHealthLine({ orgSlug, status }: SystemHealthLineProps) {
  const state = dotState(status);
  return (
    <Link
      href={`/${orgSlug}/system`}
      className="inline-flex items-center gap-2 rounded-md px-2 py-1 text-sm text-fg-muted hover:bg-bg-overlay hover:text-fg"
    >
      <span className={cn("size-2 rounded-full", DOT_CLASSES[state])} aria-hidden="true" />
      {DOT_LABELS[state]}
      <span className="text-fg-subtle">· diagnóstico</span>
    </Link>
  );
}
