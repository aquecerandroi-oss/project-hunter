import { logger } from "@/lib/logger";

/**
 * NEW (Astra, T1.5b fix pass 2): `window.localStorage` access can THROW
 * `SecurityError` -- not just return `null` -- when storage is denied
 * (Safari's "block all cookies", enterprise/managed-browser policy, some
 * private-browsing modes; HTML Storage spec). `usePriceFlash.ts` and
 * `appearance-form.tsx` used to touch `window.localStorage` directly with no
 * try/catch: for a user with storage blocked, the very first row's
 * `usePriceFlash` call threw during render and white-screened the entire
 * markets table over a cosmetic preference. Every `localStorage` touch in
 * this app must go through these two functions instead of the global
 * directly, so a blocked store degrades to "use the default, don't persist"
 * rather than crashing the page.
 */
export function readLocalStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    logger.warn("local_storage_read_failed", { key, error: String(error) });
    return null;
  }
}

export function writeLocalStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch (error) {
    logger.warn("local_storage_write_failed", { key, error: String(error) });
  }
}
