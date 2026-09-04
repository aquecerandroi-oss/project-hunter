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
 * duplicating its dark/light logic. Density sets a real `data-density`
 * attribute on `<html>`; the CSS that reacts to it lives globally in
 * `app/globals.css` (not scoped to this component), and `app/layout.tsx`'s
 * pre-hydration script (lib/pre-hydration-script.ts) applies it from
 * `localStorage` before paint -- exactly like the theme -- so the setting
 * holds on every page, not only while this screen is mounted.
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
      <section>
        <h2 className="text-sm font-medium text-fg">Tema</h2>
        <p className="mt-1 text-sm text-fg-muted">Escuro por padrão; claro disponível desde o M0.</p>
        <div className="mt-2">
          <ThemeToggle />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-medium text-fg">Densidade</h2>
        <p className="mt-1 text-sm text-fg-muted">Afeta o espaçamento do conteúdo principal.</p>
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
                density === option ? "border-gold bg-gold-soft text-fg" : "border-border bg-bg-overlay text-fg hover:border-border-strong",
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
