import Link from "next/link";

import { Button } from "@/components/ui/button";

export interface MembersCardProps {
  orgSlug: string;
  count: number;
  /** True when the roster has more pages than were counted (see the caller's page-size cap). */
  atLeast: boolean;
}

export function MembersCard({ orgSlug, count, atLeast }: MembersCardProps) {
  return (
    <section className="rounded-lg border border-border bg-surface-1 p-4">
      <h2 className="text-sm font-medium text-muted">Membros</h2>
      <p className="num mt-1 text-2xl font-semibold text-foreground">
        {atLeast ? `${count}+` : count}
      </p>
      <Button asChild variant="outline" size="sm" className="mt-3">
        <Link href={`/${orgSlug}/settings/members`}>Gerenciar membros</Link>
      </Button>
    </section>
  );
}
