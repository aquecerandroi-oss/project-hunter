/**
 * Generic loading skeleton for every route under `(app)/[orgSlug]/**`
 * (T3.24a's brief §3, fixes X1): before this file existed, navigating
 * between pages -- every one a Server Component doing 3-7 sequential fetches
 * -- gave no feedback at all until the response landed. `animate-pulse`
 * needs no extra `motion-reduce:` guard here: `globals.css`'s app-wide
 * `@media (prefers-reduced-motion: reduce)` rule already zeroes every
 * animation duration, this one included. Decorative only, no text -- a
 * screen reader gets nothing new to announce either way during a
 * transition this short.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-4" aria-hidden="true">
      <div className="h-7 w-40 animate-pulse rounded bg-bg-overlay" />
      <div className="grid gap-4 md:grid-cols-3">
        <div className="h-24 animate-pulse rounded-lg border border-border bg-bg-elevated" />
        <div className="h-24 animate-pulse rounded-lg border border-border bg-bg-elevated" />
        <div className="h-24 animate-pulse rounded-lg border border-border bg-bg-elevated" />
      </div>
    </div>
  );
}
