import { resultBadgeKind } from "@/components/lab/lab-money";

const LABEL: Record<ReturnType<typeof resultBadgeKind>, string> = {
  lucro: "lucro",
  prejuizo: "prejuízo",
  pendente: "pendente",
  neutro: "neutro",
};

const CLASS: Record<ReturnType<typeof resultBadgeKind>, string> = {
  lucro: "border-transparent bg-green/15 text-green",
  prejuizo: "border-transparent bg-red/15 text-red",
  pendente: "border-transparent bg-bg-overlay text-fg-muted",
  neutro: "border-transparent bg-bg-overlay text-fg-muted",
};

/** The "lucro"/"prejuízo"/"pendente" (plus a rare exact-zero "neutro") badge for the plain-money "Resultado" column/field (brief T3.17). */
export function ResultBadge({ pnlUsdt }: { pnlUsdt: number | null }) {
  const kind = resultBadgeKind(pnlUsdt);
  return <span className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-[11px] font-medium ${CLASS[kind]}`}>{LABEL[kind]}</span>;
}
