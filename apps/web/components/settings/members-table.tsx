"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { removeMember, updateMemberRole } from "@/lib/api/members-actions";
import { ORG_ROLES } from "@/lib/api/schemas";
import type { MemberOut, OrganizationRole } from "@/lib/api/types";

/** `apps/web/lib/format.ts` covers money/pct/compact numbers only -- a plain date formatter belongs here, its only caller. */
function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(new Date(iso));
}

export interface MembersTableProps {
  orgId: string;
  members: MemberOut[];
  /** The signed-in caller's own role. Role changes and removal are OWNER-only on the API (members.py); this only hides the controls for anyone else. */
  currentRole: OrganizationRole;
}

/** Settings > Members roster (docs/PRODUCT.md §4). Role select and remove are OWNER-only, mirroring `apps/api/hunter_api/routers/members.py`. */
export function MembersTable({ orgId, members, currentRole }: MembersTableProps) {
  const canManage = currentRole === "OWNER";

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-left">
        <thead className="bg-bg-overlay text-xs text-fg-muted">
          <tr>
            <th className="h-8 px-3 font-medium">Nome</th>
            <th className="h-8 px-3 font-medium">Email</th>
            <th className="h-8 px-3 font-medium">Papel</th>
            <th className="h-8 px-3 font-medium">Entrou em</th>
            {canManage && <th className="h-8 px-3 font-medium">Ações</th>}
          </tr>
        </thead>
        <tbody className="text-[13px]">
          {members.map((member) => (
            <MemberRow key={member.user_id} orgId={orgId} member={member} canManage={canManage} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MemberRow({ orgId, member, canManage }: { orgId: string; member: MemberOut; canManage: boolean }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, startTransition] = useTransition();

  function handleRoleChange(role: string): void {
    setError(null);
    startTransition(async () => {
      const result = await updateMemberRole(orgId, member.user_id, role);
      if (!result.ok) setError(result.problem.detail ?? result.problem.title);
      else router.refresh();
    });
  }

  function handleRemove(): void {
    setError(null);
    startTransition(async () => {
      const result = await removeMember(orgId, member.user_id);
      setConfirmOpen(false);
      if (!result.ok) setError(result.problem.detail ?? result.problem.title);
      else router.refresh();
    });
  }

  return (
    <tr className="h-8 border-t border-border">
      <td className="px-3 text-fg">{member.display_name ?? "--"}</td>
      <td className="px-3 text-fg">{member.email}</td>
      <td className="px-3">
        {canManage ? (
          <select
            value={member.role}
            disabled={pending}
            onChange={(e) => handleRoleChange(e.target.value)}
            aria-label={`Papel de ${member.email}`}
            className="h-7 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
          >
            {ORG_ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        ) : (
          member.role
        )}
      </td>
      <td className="px-3 text-fg">{member.joined_at ? formatDate(member.joined_at) : "--"}</td>
      {canManage && (
        <td className="px-3">
          <Dialog.Root open={confirmOpen} onOpenChange={setConfirmOpen}>
            <Dialog.Trigger asChild>
              <Button type="button" variant="destructive" size="sm">
                Remover
              </Button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
              <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-bg-elevated p-4 shadow-lg">
                <Dialog.Title className="text-sm font-semibold text-fg">Remover membro?</Dialog.Title>
                <Dialog.Description className="mt-2 text-sm text-fg-muted">
                  {member.email} perderá acesso a esta organização. Esta ação não pode ser desfeita pela interface.
                </Dialog.Description>
                <div className="mt-4 flex justify-end gap-2">
                  <Dialog.Close asChild>
                    <Button type="button" variant="outline" size="sm">
                      Cancelar
                    </Button>
                  </Dialog.Close>
                  <Button type="button" variant="destructive" size="sm" onClick={handleRemove} disabled={pending}>
                    {pending ? "Removendo..." : "Remover"}
                  </Button>
                </div>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        </td>
      )}
      {error && (
        <td colSpan={5} className="px-3 pb-2 text-xs text-red">
          {error}
        </td>
      )}
    </tr>
  );
}
