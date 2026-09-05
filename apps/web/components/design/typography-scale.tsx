/**
 * docs/DESIGN.md §2's 5-size scale (T1.5b joint decision #6): 12/14/16/20/28,
 * one family, `JetBrains Mono`/`tabular-nums` for every numeral regardless of
 * size -- no second "display" font for big numbers.
 */
export function TypographyScale() {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-4">
      <p className="num text-[28px] font-semibold text-fg">28px -- preço grande (detalhe do mercado, 64.230,50)</p>
      <p className="text-xl font-semibold text-fg">20px -- título de seção</p>
      <p className="text-base text-fg">16px -- texto de destaque</p>
      <p className="text-sm text-fg">14px -- texto corrido / corpo de tabela</p>
      <p className="text-xs uppercase tracking-wide text-fg-muted">12px -- labels e eyebrows</p>
    </div>
  );
}
