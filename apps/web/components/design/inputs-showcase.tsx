/** Form inputs: gold focus ring (docs/DESIGN.md §2, "anel de foco"), `red` for validation errors. */
export function InputsShowcase() {
  return (
    <div className="flex flex-wrap gap-4">
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-fg">Campo normal (foco: Tab)</span>
        <input
          placeholder="Acme Capital"
          className="rounded-md border border-border bg-bg-overlay px-3 py-2 text-sm text-fg outline-none focus-visible:ring-2 focus-visible:ring-gold"
        />
      </label>
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-fg">Campo inválido</span>
        <input
          defaultValue="abc"
          className="rounded-md border border-red bg-bg-overlay px-3 py-2 text-sm text-fg outline-none focus-visible:ring-2 focus-visible:ring-gold"
        />
        <span className="text-xs text-red">Use um número válido</span>
      </label>
    </div>
  );
}
