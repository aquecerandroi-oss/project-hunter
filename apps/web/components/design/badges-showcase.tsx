import { Badge, type BadgeProps } from "@/components/ui/badge";
import { contrastRatio } from "@/components/design/contrast";

/**
 * Hex values mirror `app/globals.css` exactly (DESIGN-5, T3.24a) -- computed
 * with both themes at once via `contrast.ts`'s pure `contrastRatio`, rather
 * than `readColorToken`'s live-DOM read (which only ever sees whichever
 * theme is currently active): a dev reviewing this page wants both numbers
 * side by side without having to toggle the theme back and forth.
 */
const STATUS_BADGES: { variant: NonNullable<BadgeProps["variant"]>; label: string; dark: [string, string]; light: [string, string] }[] = [
  { variant: "default", label: "NORMAL", dark: ["#f5f5f5", "#161616"], light: ["#0a0a0a", "#f3f3f3"] },
  { variant: "info", label: "WATCHING", dark: ["#60a5fa", "#0f1f33"], light: ["#1d4ed8", "#dbeafe"] },
  { variant: "warning", label: "ANOMALY", dark: ["#f59e0b", "#2e1f06"], light: ["#a34a05", "#fef3c7"] },
  { variant: "gold", label: "HOT", dark: ["#f2b705", "#3a2e08"], light: ["#7f6400", "#fff4d6"] },
  { variant: "positive", label: "ENTRY_CANDIDATE", dark: ["#22c55e", "#0e2a1a"], light: ["#15803d", "#dcfce7"] },
  { variant: "negative", label: "BLOCKED_BY_RISK", dark: ["#ef4444", "#2a0e0e"], light: ["#b91c1c", "#fee2e2"] },
];

/** The exact status vocabulary from docs/DESIGN.md §3, each with its measured AA ratio in both themes (DESIGN-5: solid `-soft` tokens, no more `bg-x/15` composite). */
export function BadgesShowcase() {
  return (
    <div className="flex flex-col gap-2">
      {STATUS_BADGES.map(({ variant, label, dark, light }) => {
        const darkRatio = contrastRatio(...dark);
        const lightRatio = contrastRatio(...light);
        return (
          <div key={variant} className="flex flex-wrap items-center gap-3">
            <Badge variant={variant}>{label}</Badge>
            <span className="font-mono text-xs text-fg-muted">
              escuro {darkRatio?.toFixed(2)}:1 · claro {lightRatio?.toFixed(2)}:1
            </span>
          </div>
        );
      })}
    </div>
  );
}
