/** docs/DESIGN.md §2: 24px KPI values, 14px body, 13px table body, 12px labels -- all in the mono stack for numerals. */
export function TypographyScale() {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-4">
      <p className="num text-2xl font-semibold text-fg">24px -- valor de KPI (+1.234,56)</p>
      <p className="text-sm text-fg">14px -- texto corrido / corpo padrão</p>
      <p className="text-[13px] text-fg">13px -- corpo de tabela densa</p>
      <p className="text-xs uppercase tracking-wide text-fg-muted">12px -- labels e títulos de card</p>
    </div>
  );
}
