"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { resolveMarketHrefAction } from "@/lib/api/lab-actions";
import { logger } from "@/lib/logger";

export interface LabMarketLinkProps {
  orgSlug: string;
  symbol: string;
}

/**
 * `SignalListItemOut.market` is a bare symbol with no exchange
 * (`lib/api/lab-actions.ts::resolveMarketHrefAction`'s docstring). A real
 * `<a href>` can't be built synchronously without guessing the exchange, so
 * this is a real, focusable `<button>` that resolves the honest destination
 * on click/Enter and navigates -- never a fabricated link.
 */
export function LabMarketLink({ orgSlug, symbol }: LabMarketLinkProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function open(): Promise<void> {
    setBusy(true);
    try {
      const href = await resolveMarketHrefAction(orgSlug, symbol);
      router.push(href);
    } catch (error) {
      logger.error("lab_market_link_resolve_failed", { symbol, error: String(error) });
      router.push(`/${orgSlug}/markets?q=${encodeURIComponent(symbol)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        void open();
      }}
      aria-busy={busy}
      className="font-medium text-fg underline-offset-2 hover:text-gold hover:underline disabled:opacity-60"
      disabled={busy}
    >
      {symbol}
    </button>
  );
}
