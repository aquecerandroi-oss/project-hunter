import type { SystemInfo } from "@/lib/api/types";

export interface SystemInfoCardProps {
  info: SystemInfo;
}

/** `GET /api/v1/system/info` (apps/api/hunter_api/health.py), rendered as-is -- no fabricated build metadata. */
export function SystemInfoCard({ info }: SystemInfoCardProps) {
  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong">
      <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">API</h2>
      <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
        <div>
          <dt className="text-fg-muted">Ambiente</dt>
          <dd className="text-fg">{info.environment}</dd>
        </div>
        <div>
          <dt className="text-fg-muted">Versão</dt>
          <dd className="num text-fg">{info.version}</dd>
        </div>
        <div>
          <dt className="text-fg-muted">Git SHA</dt>
          <dd className="num text-fg">{info.git_sha}</dd>
        </div>
      </dl>
    </section>
  );
}
