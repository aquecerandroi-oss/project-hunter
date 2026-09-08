import { Badge } from "@/components/ui/badge";
import { LabAsOf } from "@/components/lab/lab-as-of";
import { evidenceLabel, replicationReasonLabel, replicationStatusLabel } from "@/components/lab/labels";
import type { ReplicationBlockOut } from "@/lib/api/lab-types";

export interface LabReplicationBlockProps {
  replication: ReplicationBlockOut;
}

type ReplicationVariant = "outline" | "info" | "positive" | "negative";

const STATUS_VARIANT: Record<string, ReplicationVariant> = {
  promissora: "outline",
  replicando: "info",
  real: "positive",
  refutada: "negative",
};

interface ReasonRow {
  label: string;
  raw: string | null;
}

/**
 * The Placar card's "Replicação" block (brief T3.24b addendum A2,
 * REPLICATION.md §6): only rendered when the API sends a non-null
 * `row.replication` (`status: "none"` -- never validated -- comes back as a
 * `null` block entirely, so this component never has to render that state).
 * No new chart: every number here is text, same density as the Replay block
 * beside it.
 */
export function LabReplicationBlock({ replication }: LabReplicationBlockProps) {
  const { siblings } = replication;
  const allReasons: ReasonRow[] = [
    { label: "Fora da amostra", raw: replication.out_of_sample.reason },
    { label: "Irmãs", raw: siblings.reason },
    { label: "Metades de mercado", raw: replication.market_halves.reason },
    { label: "Bootstrap", raw: replication.bootstrap.refused_reason },
  ];
  const reasons = allReasons.filter((row): row is ReasonRow & { raw: string } => row.raw !== null);

  return (
    <div data-testid="lab-replication-block" className="mt-3 rounded-md border border-border bg-bg-overlay/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={STATUS_VARIANT[replication.status] ?? "outline"}>{replicationStatusLabel(replication.status)}</Badge>
        {replication.promising_at && (
          <span className="text-[11px] text-fg-subtle">
            promissora desde <LabAsOf iso={replication.promising_at} />
          </span>
        )}
      </div>

      <p className="mt-1.5 text-[11px] text-fg-muted">
        {`irmãs ${siblings.mature}/${siblings.n} maduras · ${siblings.positive} positivas (esperado ${siblings.expected}, exigido ${siblings.required})`}
      </p>

      {siblings.arms.length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {siblings.arms.map((arm) => (
            <li key={arm.k} className="text-[11px] text-fg-subtle">
              {`irmã ${arm.k} (${arm.version}): ${evidenceLabel(arm.evidence)}`}
            </li>
          ))}
        </ul>
      )}

      {reasons.length > 0 && (
        <ul className="mt-1.5 flex flex-col gap-0.5">
          {reasons.map((row) => (
            <li key={row.label} title={row.raw} className="text-[11px] text-fg-subtle">
              {row.label}: {replicationReasonLabel(row.raw)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
