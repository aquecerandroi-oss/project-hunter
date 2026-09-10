/**
 * The wallet-level Risk profile banner (T3.72d, brief item 1): the same
 * `riskProfileGateReason` sentence the "Nova ordem paper" gate uses
 * (`manual-order-section.tsx`), rendered once at the top of the Carteira
 * screen so a trader sees it before ever opening the form. Server Component
 * -- no interactivity, `reason` is already the exact Portuguese sentence to
 * show, never re-derived here. Renders nothing when `reason` is `null`
 * (either the profile is linked and matches the engine, or the read that
 * would tell us failed -- an honest silence, not a guess).
 */
export interface RiskProfileBannerProps {
  reason: string | null;
}

export function RiskProfileBanner({ reason }: RiskProfileBannerProps) {
  if (reason === null) return null;

  return (
    <div className="rounded-md border border-warning/40 bg-bg-elevated p-3" data-testid="risk-profile-banner">
      <p className="text-xs font-semibold text-warning">Aviso -- perfil de risco</p>
      <p className="mt-1 text-xs text-fg-muted">{reason}</p>
    </div>
  );
}
