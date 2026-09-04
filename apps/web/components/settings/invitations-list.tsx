"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { revokeInvitation } from "@/lib/api/invitations-actions";
import type { InvitationOut } from "@/lib/api/types";

export interface InvitationsListProps {
  orgId: string;
  invitations: InvitationOut[];
}

function formatExpiry(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(new Date(iso));
}

/** Settings > Members > pending invitations (ADMIN and above -- `apps/api/hunter_api/routers/invitations.py`). Never shows the token. */
export function InvitationsList({ orgId, invitations }: InvitationsListProps) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const pendingInvitations = invitations.filter((i) => !i.accepted_at);
  if (pendingInvitations.length === 0) {
    return <p className="text-sm text-fg-muted">Nenhum convite pendente.</p>;
  }

  function handleRevoke(id: string): void {
    setError(null);
    startTransition(async () => {
      const result = await revokeInvitation(orgId, id);
      if (!result.ok) setError(result.problem.detail ?? result.problem.title);
      else router.refresh();
    });
  }

  return (
    <div className="flex flex-col gap-2">
      {error && <p className="text-sm text-red">{error}</p>}
      <ul className="flex flex-col gap-2">
        {pendingInvitations.map((invitation) => (
          <li
            key={invitation.id}
            className="flex items-center justify-between gap-2 rounded-md border border-border bg-bg-overlay px-3 py-2 text-sm"
          >
            <div>
              <p className="text-fg">{invitation.email}</p>
              <p className="text-xs text-fg-muted">
                {invitation.role} · expira em {formatExpiry(invitation.expires_at)}
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => handleRevoke(invitation.id)} disabled={pending}>
              Revogar
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
