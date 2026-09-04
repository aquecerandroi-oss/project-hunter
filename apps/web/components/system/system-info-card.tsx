import type { SystemInfo } from "@/lib/api/types";

export interface SystemInfoCardProps {
  info: SystemInfo;
}

/** `GET /api/v1/system/info` (apps/api/hunter_api/health.py), rendered as-is -- no fabricated build metadata. */
export function SystemInfoCard({ info }: SystemInfoCardProps) {
  return (
    <section className="rounded-lg border border-border bg-surface-1 p-4">
      <h2 className="text-sm font-medium text-muted">API</h2>
      <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
        <div>
          <dt className="text-muted">Ambiente</dt>
          <dd className="text-foreground">{info.environment}</dd>
        </div>
        <div>
          <dt className="text-muted">Versão</dt>
          <dd className="num text-foreground">{info.version}</dd>
        </div>
        <div>
          <dt className="text-muted">Git SHA</dt>
          <dd className="num text-foreground">{info.git_sha}</dd>
        </div>
      </dl>
    </section>
  );
}
