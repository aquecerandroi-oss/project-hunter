import { LabDailyGoalDatePicker } from "@/components/lab/lab-daily-goal-date-picker";
import {
  axisNoteLine,
  betsCountsLine,
  dailyGoalReasonLabel,
  distanceToGoalLine,
  formatBrlOrReason,
  formatDailyGoalDay,
  formatUsdtOrReason,
  fxLine,
  goalStatus,
  goalStatusClass,
  hitRateLine,
  POOLED_EXPLANATION,
  requiredLines,
} from "@/components/lab/lab-daily-goal-format";
import { LabDailyGoalSparkline } from "@/components/lab/lab-daily-goal-sparkline";
import type { DecimalOrReason } from "@/components/lab/lab-format";
import { formatBrl } from "@/lib/format";
import type { DailyGoalOut } from "@/lib/api/lab-daily-goal-types";

export interface LabDailyGoalPanelProps {
  day: string;
  data: DailyGoalOut;
}

function Stat({ label, item, colorClass }: { label: string; item: DecimalOrReason; colorClass?: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs font-medium uppercase text-fg-muted">{label}</p>
      <p className={`mt-1 text-xl tabular-nums ${item.isValue ? (colorClass ?? "text-fg") : "text-fg-muted"}`}>{item.text}</p>
    </div>
  );
}

/** Median size is a reference, not the day's summed result. */
function ValueOfOneRStat({ data }: { data: DailyGoalOut }) {
  const v = data.value_of_1r;
  const hero = formatUsdtOrReason(v.real_usdt_p50, v.reason);
  const brl = formatBrlOrReason(v.real_brl_p50, v.reason ?? data.fx_reason ?? null);
  const range = v.real_brl_p10 !== null && v.real_brl_p90 !== null ? `faixa p10-p90: ${formatBrl(v.real_brl_p10)} - ${formatBrl(v.real_brl_p90)}` : null;
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs font-medium uppercase text-fg-muted">Referência de tamanho: 1 R (p50)</p>
      <p className={`mt-1 text-sm tabular-nums ${hero.isValue ? "text-fg" : "text-fg-muted"}`}>{hero.text}</p>
      <p className="mt-0.5 text-sm tabular-nums text-fg-muted">{brl.text}</p>
      {range && <p className="mt-0.5 text-[11px] text-fg-subtle">{range}</p>}
      <p className="mt-1 text-[11px] text-fg-subtle">
        rótulo fictício de onboarding (não o valor real): {formatBrl(v.label_brl)} por R
      </p>
    </div>
  );
}

/** Per-bet sum in USDT, then BRL at the observed FX rate. */
function RealProfitStat({ data }: { data: DailyGoalOut }) {
  const reason = data.progress.summed_reason ?? "summed_unavailable";
  const usdt = formatUsdtOrReason(data.progress.real_usdt_summed ?? null, reason);
  const brl = formatBrlOrReason(data.progress.real_brl_summed ?? null, data.progress.summed_reason ?? data.fx_reason ?? reason);
  const fx = fxLine(data.fx, data.fx_reason);
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs font-medium uppercase text-fg-muted">Resultado hipotético somado por aposta</p>
      <p className={`mt-1 text-2xl tabular-nums ${usdt.isValue ? "text-fg" : "text-fg-muted"}`}>{usdt.text}</p>
      <p className="mt-0.5 text-sm tabular-nums text-fg-muted">{brl.text}</p>
      <p className={`mt-1 text-[11px] ${fx.isValue ? "text-fg-subtle" : "text-fg-muted"}`}>{fx.text}</p>
      <p className="mt-1 text-[11px] text-fg-muted">
        contrafactual: soma do R de cada aposta única × seu próprio tamanho; p50 apenas como referência.
        Não é resultado executado da carteira; não simula todos os limites de posições simultâneas.
      </p>
    </div>
  );
}

function GoalStat({ data }: { data: DailyGoalOut }) {
  const status = goalStatus(data.progress, data.goal_brl);
  const colorClass = goalStatusClass(status);
  const distance = distanceToGoalLine(data.progress, data.goal_brl, data.value_of_1r.reason ?? null, data.fx_reason ?? null);
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs font-medium uppercase text-fg-muted">Meta e distância</p>
      <p className="mt-1 text-xl tabular-nums text-fg">{formatBrl(data.goal_brl)} / dia</p>
      <p className={`mt-1 text-sm tabular-nums ${distance.isValue ? colorClass : "text-fg-muted"}`}>{distance.text}</p>
    </div>
  );
}

function PortfolioNote({ data }: { data: DailyGoalOut }) {
  const notes: string[] = [];
  if (data.fx_reason) notes.push(`Câmbio: ${dailyGoalReasonLabel(data.fx_reason)}.`);
  if (data.portfolio.source === "no_portfolio") notes.push(`Carteira: ${dailyGoalReasonLabel("no_portfolio")}.`);
  else if (data.portfolio.source === "opening_anchor") notes.push(`Carteira: ${dailyGoalReasonLabel("opening_anchor")}.`);
  if (notes.length === 0) return null;
  return <p className="text-[11px] font-medium text-warning">{notes.join(" ")}</p>;
}

/**
 * "Meta diária" (brief T3.78, Everton 2026-09-10): the honest, real-money
 * daily-profit panel at the top of the Placar. Every figure comes straight
 * from `GET /api/v1/orgs/{org_id}/lab/daily-goal` (`.claude/state/notes-T3.78.md`
 * §1, `fx`/`real_usdt_*`/`unique_usdt` added additively by brief T3.78b) --
 * a `null` value here always renders its own API-given reason, never a
 * fabricated number. A pure Server Component: the only interactive piece is
 * the date picker, its own small client component.
 */
export function LabDailyGoalPanel({ day, data }: LabDailyGoalPanelProps) {
  const required = requiredLines(data.progress);
  const hitRate = hitRateLine(data.hit_rate);
  return (
    <section data-testid="lab-daily-goal-panel" className="flex flex-col gap-4 rounded-lg border border-border bg-bg-elevated p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-fg-muted">Meta diária</p>
          <p className="text-xs text-fg-muted">Dia consultado: {formatDailyGoalDay(data.day)} (Brasília)</p>
          <p className="text-xs text-fg-muted">versões ativas em cada dia, incluindo as aposentadas depois</p>
        </div>
        <LabDailyGoalDatePicker day={day} />
      </div>

      <PortfolioNote data={data} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-md border border-border p-3 sm:col-span-2">
          <p className="text-xs font-medium uppercase text-fg-muted">Apostas do dia</p>
          <p className="mt-1 text-xl tabular-nums text-fg">{betsCountsLine(data.unique_bets, data.pooled_bets)}</p>
          <p className="mt-1 text-[11px] text-fg-subtle">{POOLED_EXPLANATION}</p>
        </div>
        <Stat label="Taxa de acerto" item={hitRate} />
        <ValueOfOneRStat data={data} />
        <RealProfitStat data={data} />
        <GoalStat data={data} />
        <Stat label="O que 1 R precisaria valer" item={required.requiredOneR} />
        <Stat label="R únicos para a meta (referência p50)" item={required.requiredUniqueR} />
      </div>

      <p className="text-[11px] text-fg-subtle">{axisNoteLine(data.axis)}</p>

      <div>
        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-fg-muted">R único, últimos 30 dias</p>
        <LabDailyGoalSparkline series={data.series_30d} />
      </div>
    </section>
  );
}
