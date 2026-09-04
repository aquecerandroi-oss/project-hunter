export interface EmptyStateCardProps {
  title: string;
  message: string;
}

/**
 * An honest empty state (docs/PRODUCT.md §7: "estados vazios honestos... em
 * vez de placeholders"). Never a fake chart, never an invented number.
 */
export function EmptyStateCard({ title, message }: EmptyStateCardProps) {
  return (
    <section className="rounded-lg border border-dashed border-border bg-surface-1 p-4">
      <h2 className="text-sm font-medium text-muted">{title}</h2>
      <p className="mt-2 text-sm text-foreground">{message}</p>
    </section>
  );
}
