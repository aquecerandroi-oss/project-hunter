"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export interface LabErrorProps {
  reason: string;
}

/**
 * Honest failure state (brief S3b: "503 (API/Postgres fora): 'sem
 * verificação' != '0'"). The Shadow Lab summary/signals never render a
 * `0`/empty table in place of a real fetch failure -- that would read as
 * "zero signals" instead of "we could not check". Mirrors
 * `components/markets/markets-error.tsx`.
 */
export function LabError({ reason }: LabErrorProps) {
  const router = useRouter();
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-red/40 bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Shadow Lab indisponível (sem verificação): {reason}</p>
      <Button type="button" variant="outline" size="sm" onClick={() => router.refresh()}>
        Tentar novamente
      </Button>
    </div>
  );
}
