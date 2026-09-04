"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { acceptInvitation } from "@/lib/api/invitations-actions";

export interface AcceptInviteCardProps {
  /** `?token=` from the accept-invite link (components/settings/invite-form.tsx builds it); `null` when the link was opened without one. */
  token: string | null;
}

/**
 * `/accept-invite?token=...` -- the single primary (gold) action is
 * "Aceitar convite" (docs/DESIGN.md §2: at most one `default`-variant button
 * per screen). The organization's name is deliberately not shown here: the
 * only endpoint that resolves a bare token is the accept call itself
 * (apps/api/hunter_api/routers/invitations.py), and it consumes the token
 * as it does so -- there is no earlier "preview" read, so this says that
 * plainly instead of inventing a name or hiding the gap.
 */
export function AcceptInviteCard({ token }: AcceptInviteCardProps) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function handleAccept(): void {
    if (!token) return;
    setError(null);
    startTransition(async () => {
      const result = await acceptInvitation(token);
      if (!result.ok) {
        setError(result.problem.detail ?? result.problem.title);
        return;
      }
      router.push(`/${result.data.orgSlug}/dashboard`);
    });
  }

  return (
    <div className="w-full max-w-md rounded-lg border border-border bg-bg-elevated p-6">
      <h1 className="text-lg font-semibold text-fg">Convite para organização</h1>
      <p className="mt-2 text-sm text-fg-muted">
        O nome da organização só é revelado depois que o convite é aceito -- a API não expõe essa informação antes
        disso.
      </p>

      {!token && (
        <p role="alert" className="mt-4 rounded-md border border-red/30 bg-red/10 px-3 py-2 text-sm text-red">
          Link de convite inválido -- nenhum token foi informado.
        </p>
      )}

      {error && (
        <p role="alert" className="mt-4 rounded-md border border-red/30 bg-red/10 px-3 py-2 text-sm text-red">
          {error}
        </p>
      )}

      <Button type="button" className="mt-6 w-full" onClick={handleAccept} disabled={!token || pending}>
        {pending ? "Aceitando..." : "Aceitar convite"}
      </Button>
    </div>
  );
}
