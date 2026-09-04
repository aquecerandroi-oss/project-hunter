import { notFound } from "next/navigation";

import { DesignPreview } from "@/components/design/design-preview";

/**
 * docs/DESIGN.md §4: a design-review tool, not a feature. 404s in
 * production and is never listed in lib/nav-registry.ts.
 */
export default function DesignPreviewPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <DesignPreview />;
}
