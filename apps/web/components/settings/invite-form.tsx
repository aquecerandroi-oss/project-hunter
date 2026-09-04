"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition, type FormEvent } from "react";

import { InvitationCreatedBox } from "@/components/settings/invitation-created";
import { Button } from "@/components/ui/button";
import { createInvitation } from "@/lib/api/invitations-actions";
import { ORG_ROLES, invitationEmailSchema } from "@/lib/api/schemas";
import type { OrganizationRole } from "@/lib/api/types";

const ROLE_RANK: Record<OrganizationRole, number> = { VIEWER: 1, ANALYST: 2, TRADER: 3, ADMIN: 4, OWNER: 5 };

export interface InviteFormProps {
  orgId: string;
  /** The signed-in caller's own role -- the API refuses a role above the inviter's (`RoleAboveInviterError`); this narrows the select to what would succeed. */
  currentRole: OrganizationRole;
}

/**
 * Settings > Members > invite. `POST /api/v1/orgs/{org_id}/invitations`
 * returns the token exactly once (apps/api/hunter_api/schemas/invitations.py);
 * there is no accept page in this milestone yet (T09 does not build one),
 * so the link below points at a route a future task wires up -- the token
 * itself, and its one-time visibility, are real today.
 */
export function InviteForm({ orgId, currentRole }: InviteFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrganizationRole>("VIEWER");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ link: string; email: string } | null>(null);
  const [pending, startTransition] = useTransition();

  const allowedRoles = ORG_ROLES.filter((r) => ROLE_RANK[r] <= ROLE_RANK[currentRole]);
  const valid = invitationEmailSchema.safeParse(email).success;

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    setError(null);
    startTransition(async () => {
      const result = await createInvitation(orgId, { email, role });
      if (!result.ok) {
        setError(result.problem.detail ?? result.problem.title);
        return;
      }
      const link = `${window.location.origin}/accept-invite?token=${result.data.token}`;
      setCreated({ link, email: result.data.email });
      setEmail("");
      router.refresh();
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-fg">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="pessoa@exemplo.com"
            className="rounded-md border border-border bg-bg-overlay px-3 py-2 text-sm text-fg outline-none focus-visible:ring-2 focus-visible:ring-gold"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-fg">Papel</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as OrganizationRole)}
            className="rounded-md border border-border bg-bg-overlay px-2 py-2 text-sm text-fg"
          >
            {allowedRoles.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <Button type="submit" size="sm" disabled={!valid || pending}>
          {pending ? "Enviando..." : "Convidar"}
        </Button>
      </form>
      {error && <p className="text-sm text-red">{error}</p>}
      {created && <InvitationCreatedBox link={created.link} email={created.email} />}
    </div>
  );
}
