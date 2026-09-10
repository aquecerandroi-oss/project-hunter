"use client";

import { usePathname, useRouter } from "next/navigation";

export interface LabDailyGoalDatePickerProps {
  /** `YYYY-MM-DD`, the Brasília calendar day currently shown (`?day=`, defaulting to Brasília "today" -- brief T3.78). */
  day: string;
}

/**
 * Rewrites `?day=` on the Lab page (same URL-as-state convention as
 * `lab-filters.tsx`'s `navigate`): the Server Component re-fetches
 * `getLabDailyGoal` with the new day. A native `<input type="date">` --
 * Everton's day is a calendar day, not an instant, so this needs no time
 * component and no timezone math on the client at all.
 */
export function LabDailyGoalDatePicker({ day }: LabDailyGoalDatePickerProps) {
  const router = useRouter();
  const pathname = usePathname();

  function onChange(value: string): void {
    if (!value) return;
    const params = new URLSearchParams(window.location.search);
    params.set("day", value);
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-xs text-fg-muted">Dia (Brasília)</span>
      <input
        type="date"
        value={day}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 rounded-md border border-border-input bg-bg px-2 text-[13px] tabular-nums text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
        aria-label="Dia da meta diária, horário de Brasília"
      />
    </label>
  );
}
