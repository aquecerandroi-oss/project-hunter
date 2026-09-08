import { Button, type ButtonProps } from "@/components/ui/button";
import { contrastRatio } from "@/components/design/contrast";

/** Hex values mirror `app/globals.css` -- see `badges-showcase.tsx`'s own comment for why both themes are computed at once instead of read live off the DOM. */
const VARIANTS: { variant: NonNullable<ButtonProps["variant"]>; label: string; dark: [string, string]; light: [string, string] }[] = [
  { variant: "default", label: "Primário", dark: ["#0a0a0a", "#f2b705"], light: ["#ffffff", "#7f6400"] },
  { variant: "secondary", label: "Secundário", dark: ["#f5f5f5", "#0a0a0a"], light: ["#0a0a0a", "#ffffff"] },
  { variant: "outline", label: "Outline", dark: ["#f5f5f5", "#0a0a0a"], light: ["#0a0a0a", "#ffffff"] },
  { variant: "ghost", label: "Ghost", dark: ["#f5f5f5", "#0a0a0a"], light: ["#0a0a0a", "#ffffff"] },
  // DESIGN-5 (T3.24a): `text-bg` instead of a fixed `white` -- resolves to
  // black in dark (5.26:1) and white in light (6.47:1), both >= AA, unlike
  // the old fixed white (3.76:1 in dark).
  { variant: "destructive", label: "Destrutivo", dark: ["#0a0a0a", "#ef4444"], light: ["#ffffff", "#b91c1c"] },
];

/** docs/DESIGN.md §3: gold primary is rare -- one per screen -- secondary is bordered, destructive is red. Each with its measured AA ratio in both themes. */
export function ButtonsShowcase() {
  return (
    <div className="flex flex-col gap-2">
      {VARIANTS.map(({ variant, label, dark, light }) => {
        const darkRatio = contrastRatio(...dark);
        const lightRatio = contrastRatio(...light);
        return (
          <div key={variant} className="flex flex-wrap items-center gap-3">
            <Button variant={variant}>{label}</Button>
            <span className="font-mono text-xs text-fg-muted">
              escuro {darkRatio?.toFixed(2)}:1 · claro {lightRatio?.toFixed(2)}:1
            </span>
          </div>
        );
      })}
    </div>
  );
}
