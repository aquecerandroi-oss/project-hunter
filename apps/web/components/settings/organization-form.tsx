"use client";

import { useState, useTransition, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { updateOrganization } from "@/lib/api/organizations-actions";
import { organizationNameSchema } from "@/lib/api/schemas";

export interface OrganizationFormProps {
  orgId: string;
  initialName: string;
  /** ADMIN and above -- mirrors `require_org(OrganizationRole.ADMIN)` on `PATCH /api/v1/orgs/{org_id}`. The API is the real gate; this only hides the control. */
  canEdit: boolean;
}

export function OrganizationForm({ orgId, initialName, canEdit }: OrganizationFormProps) {
  const [name, setName] = useState(initialName);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, startTransition] = useTransition();

  const valid = organizationNameSchema.safeParse(name).success;

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    setError(null);
    setSaved(false);
    startTransition(async () => {
      const result = await updateOrganization(orgId, name);
      if (!result.ok) {
        setError(result.problem.detail ?? result.problem.title);
        return;
      }
      setSaved(true);
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">Nome da organização</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={!canEdit}
          maxLength={120}
          className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
        />
      </label>
      {!canEdit && (
        <p className="text-xs text-muted">Somente Admin ou Owner podem renomear a organização.</p>
      )}
      {error && <p className="text-sm text-negative">{error}</p>}
      {saved && !error && <p className="text-sm text-positive">Salvo.</p>}
      {canEdit && (
        <Button type="submit" size="sm" className="self-start" disabled={pending || !valid || name === initialName}>
          {pending ? "Salvando..." : "Salvar"}
        </Button>
      )}
    </form>
  );
}
