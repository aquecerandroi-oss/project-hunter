import Link from "next/link";

import { Button } from "@/components/ui/button";

export interface QuickLinksProps {
  orgSlug: string;
}

export function QuickLinks({ orgSlug }: QuickLinksProps) {
  return (
    <section className="flex flex-wrap gap-2 rounded-lg border border-border bg-surface-1 p-4">
      <Button asChild variant="secondary" size="sm">
        <Link href={`/${orgSlug}/settings/organization`}>Settings</Link>
      </Button>
      <Button asChild variant="secondary" size="sm">
        <Link href={`/${orgSlug}/settings/members`}>Membros</Link>
      </Button>
      <Button asChild variant="secondary" size="sm">
        <Link href={`/${orgSlug}/system`}>System</Link>
      </Button>
    </section>
  );
}
