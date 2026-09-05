"use client";

import { useEffect, useRef, useState } from "react";

import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import { readLocalStorage, writeLocalStorage } from "@/lib/safe-storage";

/**
 * Calm price flash (docs/DESIGN.md §2, joint decision #4): the background of
 * a price cell tints green/red for `FLASH_DURATION_MS` only when the value
 * actually changes, at most once per `MIN_INTERVAL_MS` per row, and never
 * when the user turned it off (persisted in `localStorage`) or asked the OS
 * for reduced motion. Never the text colour -- that stays the row's
 * standing semantic colour (24h change), so a flashing background can't be
 * confused with a positive/negative reading.
 */
export type FlashDirection = "up" | "down" | null;

const STORAGE_KEY = "hunter-price-flash-enabled";
const CHANGE_EVENT = "hunter-price-flash-change";
export const FLASH_DURATION_MS = 300;
/** At most one flash per row per 2s (joint decision #10's "calm" acceptance test). */
export const MIN_FLASH_INTERVAL_MS = 2000;

export function isPriceFlashEnabled(): boolean {
  if (typeof window === "undefined") return true;
  // NEW (Astra, T1.5b fix pass 2): a blocked store must degrade to the
  // default ("on"), never throw out of render -- see `lib/safe-storage.ts`.
  return readLocalStorage(STORAGE_KEY) !== "off";
}

/** Flips the persisted setting and notifies every mounted `usePriceFlash` row in this tab. */
export function setPriceFlashEnabled(enabled: boolean): void {
  writeLocalStorage(STORAGE_KEY, enabled ? "on" : "off");
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function usePriceFlash(value: string | null | undefined): FlashDirection {
  const reducedMotion = usePrefersReducedMotion();
  const [enabled, setEnabled] = useState(isPriceFlashEnabled);
  const [direction, setDirection] = useState<FlashDirection>(null);
  const previousRef = useRef(value);
  const lastFlashAtRef = useRef(0);

  useEffect(() => {
    // `enabled`'s `useState(isPriceFlashEnabled)` initializer already reads
    // the current value at mount -- no need to also call `setEnabled`
    // synchronously here, only to subscribe for later changes.
    function sync() {
      setEnabled(isPriceFlashEnabled());
    }
    window.addEventListener(CHANGE_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(CHANGE_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  // Detects a real change and decides whether to flash -- this effect's
  // ONLY job is choosing `direction`, never clearing it. Splitting that out
  // (below) fixes a real bug (T1.5b Astra must-fix #5): when this used to
  // also `setTimeout(() => setDirection(null), ...)` and return it as this
  // effect's own cleanup, a SECOND tick arriving before the timeout fired
  // (even one blocked by the rate limiter, which never re-flashes) still
  // tore down that cleanup -- cancelling the pending "clear the flash"
  // timeout -- and then returned early without scheduling a replacement.
  // The flash was left stuck on until some unrelated, later, non-blocked
  // change happened to reset it.
  useEffect(() => {
    const previous = previousRef.current;
    previousRef.current = value;
    if (!enabled || reducedMotion) return;

    const previousNum = toNumber(previous);
    const nextNum = toNumber(value);
    if (previousNum === null || nextNum === null || previousNum === nextNum) return;

    const now = Date.now();
    if (now - lastFlashAtRef.current < MIN_FLASH_INTERVAL_MS) return;
    lastFlashAtRef.current = now;

    setDirection(nextNum > previousNum ? "up" : "down");
  }, [value, enabled, reducedMotion]);

  // Clears the flash `FLASH_DURATION_MS` after it was actually set -- keyed
  // on `direction` itself, so a rate-limited (ignored) tick above, which
  // never changes `direction`, can never retrigger or cancel this timer.
  useEffect(() => {
    if (direction === null) return undefined;
    const timeout = setTimeout(() => setDirection(null), FLASH_DURATION_MS);
    return () => clearTimeout(timeout);
  }, [direction]);

  return direction;
}
