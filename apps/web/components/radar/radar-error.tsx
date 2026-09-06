"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export interface RadarErrorProps {
  reason: string;
}

/** Full-width honest failure state, same shape as `markets-error.tsx`: a fetch failure is a different fact from "no episode scored yet" (`RadarEmpty`). */
export function RadarError({ reason }: RadarErrorProps) {
  const router = useRouter();
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-red/40 bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Radar indisponível: {reason}</p>
      <Button type="button" variant="outline" size="sm" onClick={() => router.refresh()}>
        Tentar novamente
      </Button>
    </div>
  );
}
