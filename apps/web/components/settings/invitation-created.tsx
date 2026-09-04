"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export interface InvitationCreatedBoxProps {
  /** The full invite link, already built from the one-time token (apps/api/hunter_api/schemas/invitations.py). */
  link: string;
  email: string;
}

/**
 * Shown exactly once, right after `createInvitation` succeeds -- the API
 * stores only the token's SHA-256 hash, so this is the only moment the link
 * is ever visible again. Losing it means revoking and re-inviting.
 */
export function InvitationCreatedBox({ link, email }: InvitationCreatedBoxProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy(): Promise<void> {
    await navigator.clipboard.writeText(link);
    setCopied(true);
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-gold/40 bg-bg-overlay p-3 text-sm">
      <p className="font-medium text-fg">Convite para {email} criado.</p>
      <p className="text-xs text-warning">
        Copie este link agora -- ele não pode ser recuperado depois de sair desta tela.
      </p>
      <div className="flex items-center gap-2">
        <code className="num flex-1 truncate rounded bg-bg-overlay px-2 py-1 text-xs text-fg">{link}</code>
        <Button type="button" variant="outline" size="sm" onClick={() => void handleCopy()}>
          {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
          {copied ? "Copiado" : "Copiar"}
        </Button>
      </div>
    </div>
  );
}
