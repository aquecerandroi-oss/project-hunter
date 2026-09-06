"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export interface OpportunitiesErrorProps {
  reason: string;
}

export function OpportunitiesError({ reason }: OpportunitiesErrorProps) {
  const router = useRouter();
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-red/40 bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Oportunidades indisponíveis: {reason}</p>
      <Button type="button" variant="outline" size="sm" onClick={() => router.refresh()}>
        Tentar novamente
      </Button>
    </div>
  );
}
