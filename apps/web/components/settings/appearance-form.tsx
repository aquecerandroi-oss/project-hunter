"use client";

import { useEffect, useState } from "react";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { isPriceFlashEnabled, setPriceFlashEnabled } from "@/hooks/usePriceFlash";
import { readLocalStorage, writeLocalStorage } from "@/lib/safe-storage";
import { cn } from "@/lib/utils";

type Density = "comfortable" | "compact";

const DENSITY_KEY = "hunter-density";
const DEFAULT_DENSITY: Density = "comfortable";

function applyDensity(density: Density): void {
  document.documentElement.setAttribute("data-density", density);
  // NEW (Astra, T1.5b fix pass 2): routed through `lib/safe-storage.ts` --
  // a blocked store (SecurityError) must not crash this screen, it just
  // fails to persist the choice for next load.
  writeLocalStorage(DENSITY_KEY, density);
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
  // Fixed default (M1, T1.5b fix pass): a lazy `useState(isPriceFlashEnabled)`
  // initializer reads `localStorage` directly, which SSR always sees as
  // unset (`isPriceFlashEnabled` returns `true` with no `window`) -- a user
  // who turned the flash off hydrates from `true`/"ligado"/`aria-checked=
  // "true"` to `false`, a text + `aria-checked` mismatch on every load of
  // this screen. Same fixed-default-then-`useEffect` pattern as `density`
  // just above.
  const [priceFlash, setPriceFlash] = useState<boolean>(true);

  useEffect(() => {
    const stored = readLocalStorage(DENSITY_KEY);
    const initial: Density = stored === "compact" ? "compact" : "comfortable";
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from localStorage, an external system, on mount
    setDensity(initial);
    document.documentElement.setAttribute("data-density", initial);
    setPriceFlash(isPriceFlashEnabled());
  }, []);

  function choose(next: Density): void {
    setDensity(next);
    applyDensity(next);
  }

  function togglePriceFlash(): void {
    const next = !priceFlash;
    setPriceFlash(next);
    setPriceFlashEnabled(next);
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

      <section>
        <h2 className="text-sm font-medium text-fg">Flash de preço</h2>
        <p className="mt-1 text-sm text-fg-muted">
          Pisca o fundo do preço na tabela de mercados quando o valor muda (no máximo 1x a cada 2s por linha).
        </p>
        {/*
         * T1.5b Astra must-fix #5: this was previously only reachable from
         * the dev-only `/_design` preview -- a real user distracted by the
         * flash had no way to turn it off. `hooks/usePriceFlash.ts` persists
         * the same `localStorage` key this reads/writes.
         */}
        <div className="mt-2">
          <button
            type="button"
            role="switch"
            aria-checked={priceFlash}
            onClick={togglePriceFlash}
            className={cn(
              "rounded-md border px-3 py-2 text-sm font-medium transition-colors",
              priceFlash ? "border-gold bg-gold-soft text-fg" : "border-border bg-bg-overlay text-fg hover:border-border-strong",
            )}
          >
            Flash de preço: {priceFlash ? "ligado" : "desligado"}
          </button>
        </div>
      </section>
    </div>
  );
}
