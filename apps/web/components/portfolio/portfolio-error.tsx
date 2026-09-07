"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export interface PortfolioErrorProps {
  reason: string;
}

/** Full-width honest failure state, same shape as `RadarError`/`LabError`: a fetch failure is a different fact from "no wallet open yet" (`PortfolioEmpty`). */
export function PortfolioError({ reason }: PortfolioErrorProps) {
  const router = useRouter();
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-red/40 bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Carteira indisponível: {reason}</p>
      <Button type="button" variant="outline" size="sm" onClick={() => router.refresh()}>
        Tentar novamente
      </Button>
    </div>
  );
}
