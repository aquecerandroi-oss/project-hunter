"use client";

import { useEffect, useState } from "react";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { cn } from "@/lib/utils";

type Density = "comfortable" | "compact";

const DENSITY_KEY = "hunter-density";
const DEFAULT_DENSITY: Density = "comfortable";

function applyDensity(density: Density): void {
  document.documentElement.setAttribute("data-density", density);
  window.localStorage.setItem(DENSITY_KEY, density);
}

/**
 * Settings > Appearance (docs/PRODUCT.md §4/§7). Reuses the existing
 * `ThemeToggle` (components/layout/theme-toggle.tsx, T08) rather than
 * duplicating its dark/light logic. Density is new here: it sets a real
 * `data-density` attribute on `<html>` and ships the (tiny) CSS that reacts
 * to it inline, since this component's file is the only one in scope to
 * carry it -- a toggle with no visible effect would be exactly the "inert
 * control" CLAUDE.md rules out.
 *
 * Caveat, stated rather than hidden: unlike the theme (which `app/layout.tsx`
 * applies before paint via an inline script), density is only re-applied
 * once this component mounts. A hard refresh on a different page resets to
 * "comfortable" until Settings > Appearance is visited again in that
 * session -- out of this task's file set to fix (it would need the same
 * pre-paint script `app/layout.tsx` already has for theme).
 */
export function AppearanceForm() {
  const [density, setDensity] = useState<Density>(DEFAULT_DENSITY);

  useEffect(() => {
    const stored = window.localStorage.getItem(DENSITY_KEY);
    const initial: Density = stored === "compact" ? "compact" : "comfortable";
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from localStorage, an external system, on mount
    setDensity(initial);
    document.documentElement.setAttribute("data-density", initial);
  }, []);

  function choose(next: Density): void {
    setDensity(next);
    applyDensity(next);
  }

  return (
    <div className="flex flex-col gap-6">
      <style>{`
        [data-density="compact"] main { padding: 0.5rem !important; }
        [data-density="compact"] .density-tight { padding: 0.5rem !important; gap: 0.5rem !important; }
      `}</style>

      <section>
        <h2 className="text-sm font-medium text-foreground">Tema</h2>
        <p className="mt-1 text-sm text-muted">Escuro por padrão; claro disponível desde o M0.</p>
        <div className="mt-2">
          <ThemeToggle />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-medium text-foreground">Densidade</h2>
        <p className="mt-1 text-sm text-muted">Afeta o espaçamento do conteúdo principal.</p>
        <div className="mt-2 flex gap-2" role="radiogroup" aria-label="Densidade">
          {(["comfortable", "compact"] as const).map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={density === option}
              onClick={() => choose(option)}
              className={cn(
                "rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                density === option ? "border-accent bg-surface-3 text-foreground" : "border-border bg-surface-2 text-foreground hover:bg-surface-3",
              )}
            >
              {option === "comfortable" ? "Confortável" : "Compacta"}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
