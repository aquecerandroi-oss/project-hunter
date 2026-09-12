/**
 * "Executor real" (T4.17 deliverable 1) -- the panel above the proposals on
 * `/meme/mesa`, reading `GET /meme/live` alone. Three states, each with its
 * own honest sentence (never a placeholder chart, never an invented number):
 * `ausente` (the process itself never proved it is up), `desligado` (alive,
 * `ENABLE_MEME_LIVE_TRADING` off in the executor), `ligado` (every field the
 * heartbeat carries). Server Component -- nothing here is interactive.
 */
import { BrasiliaShort } from "@/components/time/brasilia-instant";
import { Badge } from "@/components/ui/badge";
import { SectionUnavailable } from "@/components/ui/section-unavailable";
import { computeAgeMs, formatAge } from "@/hooks/useAgeTicker";
import { type LiveExecutor, type MemeLive, executorPanelState } from "@/lib/api/meme-live-types";

import { executorStatusLabel, killSwitchBadgeVariant, killSwitchStateLabel } from "./labels";
import { gatesLines, killSwitchSourceLines, policyLines, truncateAddress } from "./live-format";
import { RealBadge } from "./real-confirm";
import { executorRefusalLabel } from "./refusal-labels";

function formatSolPlain(value: string | null | undefined): string {
  return value ? `${value} SOL` : "sem leitura";
}

function AgeNote({ iso, nowMs }: { iso: string | null | undefined; nowMs: number }) {
  const age = computeAgeMs(iso, nowMs);
  if (age === null) return <span className="text-fg-subtle">sem leitura</span>;
  return <span className="text-fg-subtle">atualizado há {formatAge(age)}</span>;
}

function PanelHeader({ executor, apiLiveEnabled, state }: { executor: LiveExecutor; apiLiveEnabled: boolean; state: string }) {
  const dot = state === "ligado" ? "bg-green" : state === "desligado" ? "bg-warning" : "bg-red";
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <RealBadge />
        <h2 className="text-sm font-semibold text-fg">Executor real</h2>
        <span className="inline-flex items-center gap-1.5 text-xs text-fg-muted">
          <span aria-hidden="true" className={`inline-block size-2 rounded-full ${dot}`} />
          {executorStatusLabel(executor.status)}
        </span>
      </div>
      {!apiLiveEnabled && (
        <p className="text-[11px] font-medium text-warning">
          A API está com o dinheiro real desligado (ENABLE_MEME_LIVE_TRADING) — "Aprovar (REAL)" fica indisponível mesmo com o executor ligado.
        </p>
      )}
    </div>
  );
}

function AusenteBody({ executor }: { executor: LiveExecutor }) {
  return (
    <div className="flex flex-col gap-1 text-xs text-fg-muted">
      <p className="text-sm text-fg">O perfil meme-live não está no ar.</p>
      <p>{executorStatusLabel(executor.status)}{executor.error ? ` (${executor.error})` : ""}</p>
      {executor.executor_ts && (
        <p>
          último sinal em <BrasiliaShort iso={executor.executor_ts} />
        </p>
      )}
    </div>
  );
}

function DesligadoBody({ executor }: { executor: LiveExecutor }) {
  return (
    <div className="flex flex-col gap-1 text-xs text-fg-muted">
      <p className="text-sm text-fg">O executor está no ar, mas o dinheiro real está desligado nele (ENABLE_MEME_LIVE_TRADING).</p>
      {executor.executor_ts && (
        <p>
          última leitura em <BrasiliaShort iso={executor.executor_ts} />
        </p>
      )}
    </div>
  );
}

function WalletBlock({ executor, nowMs }: { executor: LiveExecutor; nowMs: number }) {
  return (
    <div className="text-xs">
      <p className="font-medium text-fg-muted">Carteira</p>
      <p className="font-mono tabular-nums text-fg">
        {executor.wallet_pubkey ? truncateAddress(executor.wallet_pubkey) : "sem leitura"} · {formatSolPlain(executor.wallet_sol_balance)}
      </p>
      <AgeNote iso={executor.wallet_read_at} nowMs={nowMs} />
    </div>
  );
}

function ListBlock({ title, lines }: { title: string; lines: string[] }) {
  return (
    <div className="text-xs">
      <p className="font-medium text-fg-muted">{title}</p>
      <ul className="list-disc pl-4 text-fg">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </div>
  );
}

function KillSwitchBlock({ executor }: { executor: LiveExecutor }) {
  const effective = executor.kill_switch ?? "";
  return (
    <div className="text-xs">
      <p className="font-medium text-fg-muted">Corta-circuito</p>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={killSwitchBadgeVariant(effective)}>{killSwitchStateLabel(effective)}</Badge>
        {executor.kill_switch_latched && <Badge variant="negative">travado (só o dono destrava)</Badge>}
      </div>
      {executor.kill_switch_latch_reason && <p className="mt-1 text-fg-muted">motivo da trava: {executor.kill_switch_latch_reason}</p>}
      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-fg-muted">
        {killSwitchSourceLines(executor.kill_switch_sources).map((source) => (
          <li key={source.key}>
            {source.label}: {killSwitchStateLabel(source.value)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DayLossBlock({ executor }: { executor: LiveExecutor }) {
  const cap = executor.daily_loss_sol !== null && executor.day_start_sol_equity !== null;
  return (
    <div className="text-xs">
      <p className="font-medium text-fg-muted">Perda do dia</p>
      {cap ? (
        <p className="font-mono tabular-nums text-fg">
          {formatSolPlain(executor.daily_loss_sol)} perdidos hoje · equity {formatSolPlain(executor.equity_sol)} · início do dia {formatSolPlain(executor.day_start_sol_equity)}
        </p>
      ) : (
        <p className="text-fg-muted">sem leitura do dia (âncora ainda não gravada)</p>
      )}
    </div>
  );
}

function OrdersAndPositions({ executor }: { executor: LiveExecutor }) {
  const entries = Object.entries(executor.orders_by_state);
  return (
    <div className="text-xs">
      <p className="font-medium text-fg-muted">Ordens e posições</p>
      <p className="text-fg">posições abertas: {executor.positions_open ?? 0}</p>
      {entries.length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-2">
          {entries.map(([state, count]) => (
            <li key={state} className="rounded-md bg-bg-overlay px-1.5 py-0.5 font-mono tabular-nums text-fg-muted">
              {state}: {count}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function BlockedExitsBlock({ executor }: { executor: LiveExecutor }) {
  const entries = Object.entries(executor.blocked_exits);
  if (entries.length === 0) return null;
  return (
    <div className="text-xs">
      <p className="font-medium text-warning">Saídas bloqueadas</p>
      <ul className="list-disc pl-4 text-fg">
        {entries.map(([positionId, reason]) => (
          <li key={positionId}>
            posição {positionId.slice(0, 8)}: {executorRefusalLabel(reason) ?? reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

function LigadoBody({ live, nowMs }: { live: MemeLive; nowMs: number }) {
  const { executor } = live;
  const refusal = executorRefusalLabel(executor.last_refusal);
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <WalletBlock executor={executor} nowMs={nowMs} />
      <DayLossBlock executor={executor} />
      <ListBlock title="Tetos (policy)" lines={policyLines(executor.policy)} />
      <ListBlock title="Portões" lines={gatesLines(executor.gates)} />
      <KillSwitchBlock executor={executor} />
      <OrdersAndPositions executor={executor} />
      <BlockedExitsBlock executor={executor} />
      {refusal && (
        <div className="text-xs">
          <p className="font-medium text-warning">Última recusa</p>
          <p className="text-fg">{refusal}</p>
        </div>
      )}
    </div>
  );
}

export interface LiveExecutorPanelProps {
  live: MemeLive | null;
  loadReason: string | null;
  nowMs: number;
}

export function LiveExecutorPanel({ live, loadReason, nowMs }: LiveExecutorPanelProps) {
  if (!live) return <SectionUnavailable title="Executor real" reason={loadReason ?? "falha ao carregar"} />;
  const state = executorPanelState(live.executor);
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-red/30 bg-bg-elevated p-4">
      <PanelHeader executor={live.executor} apiLiveEnabled={live.api_live_enabled} state={state} />
      {state === "ausente" && <AusenteBody executor={live.executor} />}
      {state === "desligado" && <DesligadoBody executor={live.executor} />}
      {state === "ligado" && <LigadoBody live={live} nowMs={nowMs} />}
    </section>
  );
}
