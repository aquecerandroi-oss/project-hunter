"use client";

/**
 * "Carteira real" (T4.57) -- the client island that owns the 10 s poll
 * (`useWalletSummaryPoll`) and renders `WalletSummaryView`. Mounted once at
 * the top of `/meme/mesa`, above every other panel (Everton, 18/09/2026:
 * "a carteira precisa estar mostrando o resultado real agora").
 */
import { useWalletSummaryPoll } from "@/hooks/useWalletSummaryPoll";

import { WalletSummaryView } from "./wallet-summary-view";

export function WalletSummaryPanel({ orgId }: { orgId: string }) {
  const { summary, reason } = useWalletSummaryPoll(orgId);
  return <WalletSummaryView summary={summary} reason={reason} />;
}
