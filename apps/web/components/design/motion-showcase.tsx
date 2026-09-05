"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { isPriceFlashEnabled, setPriceFlashEnabled, usePriceFlash } from "@/hooks/usePriceFlash";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import { cn } from "@/lib/utils";

const START_PRICE = 65000;

/**
 * Live demo of `hooks/usePriceFlash.ts` (T1.5b joint decision #4): the
 * background of a price cell tints briefly on a real value change, rate
 * limited to at most once every 2s, off switch persisted in `localStorage`,
 * and gated by `prefers-reduced-motion`. Not decorative -- clicking the
 * buttons drives the exact same hook the markets table uses.
 */
export function MotionShowcase() {
  const [price, setPrice] = useState(START_PRICE);
  // Fixed default (M1, T1.5b fix pass): same SSR/hydration mismatch as
  // `components/settings/appearance-form.tsx`'s own `priceFlash` field --
  // `isPriceFlashEnabled()` reads `localStorage`, which SSR always sees as
  // unset. Corrected in the mount effect below instead.
  const [enabled, setEnabled] = useState(true);
  const reducedMotion = usePrefersReducedMotion();
  const flash = usePriceFlash(String(price));

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from localStorage, an external system, on mount
    setEnabled(isPriceFlashEnabled());
  }, []);

  function bump(direction: 1 | -1): void {
    setPrice((prev) => prev + direction * 5);
  }

  function toggle(): void {
    const next = !enabled;
    setEnabled(next);
    setPriceFlashEnabled(next);
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border p-4">
      <div className="flex items-center gap-3">
        <span
          className={cn(
            "num rounded px-2 py-1 text-lg text-fg",
            flash === "up" && "flash-up",
            flash === "down" && "flash-down",
          )}
        >
          {price.toFixed(2)}
        </span>
        <Button type="button" size="sm" variant="outline" onClick={() => bump(1)}>
          Subir
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => bump(-1)}>
          Descer
        </Button>
        <Button type="button" size="sm" variant="secondary" onClick={toggle}>
          Flash: {enabled ? "ligado" : "desligado"}
        </Button>
      </div>
      <p className="text-xs text-fg-muted">
        No máximo 1 flash a cada 2s por linha; nunca a cor do texto, só o fundo.
        {reducedMotion && " prefers-reduced-motion detectado -- flash desativado nesta sessão."}
      </p>
    </div>
  );
}
