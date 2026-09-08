/**
 * docs/DESIGN.md §2's 7-step named scale (DESIGN-5, 2026-09-08 -- the old
 * 5-size scale + exceptions no longer described the interface: `11px`
 * appeared in 36 places and `18px` in 16). One family, `JetBrains Mono`/
 * `tabular-nums` for every numeral regardless of size -- no second "display"
 * font for big numbers. `10px` and `18px` are now forbidden (the command
 * palette's `Ctrl K` hint is the one living exception to `10px`).
 */
const TYPE_SCALE: { px: string; name: string; sample: string; className: string }[] = [
  { px: "11px", name: "micro", sample: "metadado de uma linha: idade, código de exchange, cobertura, kbd", className: "text-[11px] text-fg-subtle" },
  { px: "12px", name: "label / eyebrow", sample: "PATRIMÔNIO (USDT)", className: "text-xs uppercase tracking-wide text-fg-muted" },
  { px: "13px", name: "corpo de tabela de dados", sample: "BTCUSDT · Binance · 64.230,50", className: "text-[13px] text-fg" },
  { px: "14px", name: "texto", sample: "Nenhuma posição aberta ainda.", className: "text-sm text-fg" },
  { px: "16px", name: "destaque", sample: "Consultado em 08/09/2026 14:32:10", className: "text-base text-fg" },
  { px: "20px", name: "título de seção / valor de stat", sample: "Carteira ever-01", className: "text-xl font-semibold text-fg" },
  { px: "24px", name: "KPI em grade", sample: "100,000.00 USDT", className: "num text-2xl font-semibold text-fg" },
  { px: "28px", name: "número-herói (um por tela)", sample: "64.230,50", className: "num text-[28px] font-semibold text-fg" },
];

export function TypographyScale() {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-4">
      {TYPE_SCALE.map((step) => (
        <p key={step.px} className={step.className}>
          <span className="mr-2 font-mono text-fg-subtle">
            {step.px} -- {step.name}:
          </span>
          {step.sample}
        </p>
      ))}
    </div>
  );
}
