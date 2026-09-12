import Link from "next/link";

import { betLegLabel, exitReasonLabel } from "@/components/meme-desk/labels";
import { formatMemePct, formatSol } from "@/components/meme/meme-format";
import type { MemeTestLabContext, MemeTestRow } from "@/lib/api/meme-tests-types";
import { formatMoney } from "@/lib/format";
import { formatBrasiliaLong } from "@/lib/time";

import { labContextReasonLabel, lineReasonLabel, pnlUsdBasisLabel, pnlUsdReasonLabel, yesNoLabel } from "./labels";
import { betDetailHref } from "./meme-tests-format";

export interface MemeTestRowDetailProps {
  orgSlug: string;
  row: MemeTestRow;
  /** The bet page already is the record -- no link to itself. */
  withDetailLink?: boolean;
}

const ABSENT = "não registrado";

function Field({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col">
      <dt className="text-[11px] uppercase tracking-wide text-fg-subtle">{label}</dt>
      <dd className={`${mono ? "font-mono tabular-nums" : ""} text-[13px] text-fg`}>{value}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1">
      <h4 className="text-[11px] font-medium uppercase tracking-wide text-fg-muted">{title}</h4>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 md:grid-cols-4">{children}</dl>
    </section>
  );
}

/** `null` is the honest absence; anything else goes through `fmt`. */
function show<T>(value: T | null, fmt: (value: T) => string): string {
  return value === null ? ABSENT : fmt(value);
}

/** The raw decimal string the API sent IS the precision to show (DESIGN.md §2) -- a marginal price is never rounded here. */
const price = (value: string): string => `${value} SOL/token`;
const sol4 = (value: string): string => formatSol(value, 4);
const sol2 = (value: string): string => formatSol(value, 2);
const tokens = (value: string): string => formatMoney(value, { currency: "USD", decimals: 0 }).replace(/[^0-9.,-]/g, "");
const when = (iso: string): string => formatBrasiliaLong(iso) ?? "--";
const withReason = (reason: string | null): string => (reason ? ` (${reason})` : "");

const TRIGGER_LABEL: Record<string, string> = { rules: "regra do conjunto", operator: "ordem do operador", wallet: "carteira observada" };

function EntrySection({ row }: { row: MemeTestRow }) {
  const { entry } = row;
  const fee = entry.fee_sol === null ? ABSENT : `${formatSol(entry.fee_sol, 6)}${entry.fee_pct ? ` (${entry.fee_pct} %)` : ""}`;
  const delay = entry.fill_delay_s === null ? ABSENT : `${entry.fill_delay_s} s${entry.fill_delay_snapshots === null ? "" : ` · ${entry.fill_delay_snapshots} fotografia(s)`}`;
  return (
    <Section title="Entrada">
      <Field label="Hora (Brasília)" value={when(entry.at)} />
      <Field label="Preço marginal" value={show(entry.price_sol_per_token, price)} />
      <Field label="Preço médio pago" value={show(entry.average_price_sol, price)} />
      <Field label="Mcap na fotografia" value={show(entry.mcap_sol, sol2)} />
      <Field label="SOL gasto" value={show(entry.sol_spent, sol4)} />
      <Field label="Tokens" value={show(entry.tokens, tokens)} />
      <Field label="Taxa" value={fee} />
      <Field label="Atraso do fill" value={delay} />
      <Field label="Fonte da fotografia" value={entry.source ?? ABSENT} mono={false} />
    </Section>
  );
}

function ExitSection({ row }: { row: MemeTestRow }) {
  const { exit } = row;
  return (
    <Section title={exit.provisional ? "Saída provisória (marca atual)" : "Saída"}>
      <Field label="Hora (Brasília)" value={show(exit.at, when)} />
      <Field label="Preço marginal após" value={show(exit.price_sol_per_token, price)} />
      <Field label="Mcap na fotografia" value={show(exit.mcap_sol, sol2)} />
      <Field label="SOL recebido" value={show(exit.sol_received, sol4)} />
      <Field label="Taxa" value={show(exit.fee_sol, (v) => formatSol(v, 6))} />
      <Field label="Motivo" value={exit.reason_label} mono={false} />
      <Field label="Gatilho" value={show(exit.trigger, (t) => TRIGGER_LABEL[t] ?? t)} mono={false} />
      {exit.pending_reason && <Field label="Regra que esperava fotografia" value={exitReasonLabel(exit.pending_reason)} mono={false} />}
    </Section>
  );
}

function QuoteSection({ row }: { row: MemeTestRow }) {
  return (
    <Section title="Cotação SOL/USD">
      <Field label="Na entrada" value={show(row.sol_usd_at_entry, (v) => `US$ ${v}`)} />
      <Field label="Na saída" value={show(row.sol_usd_at_exit, (v) => `US$ ${v}`)} />
      <Field label="Fonte" value={row.sol_usd_source ?? ABSENT} mono={false} />
      <Field label="Base do PnL US$" value={pnlUsdBasisLabel(row.pnl_usd_basis) ?? pnlUsdReasonLabel(row.pnl_usd_reason)} mono={false} />
    </Section>
  );
}

function LabReadings({ lab }: { lab: MemeTestLabContext }) {
  const hype = lab.hype_score === null ? `sem leitura${withReason(lab.hype_reason)}` : `${lab.hype_score}${lab.hype_reason === "partial" ? " (parcial)" : ""}`;
  const creator = yesNoLabel(lab.creator_sold, `sem leitura${withReason(lab.creator_sold_reason)}`);
  const progress = lab.curve_progress_pct === null ? `sem leitura${withReason(lab.progress_reason)}` : formatMemePct(lab.curve_progress_pct);
  return (
    <>
      <Field label="Linha traçável?" value={lab.line_drawn ? "sim" : `não — ${lineReasonLabel(lab.line_reason)}`} mono={false} />
      <Field label="Suporte" value={show(lab.support_line_sol, sol2)} />
      <Field label="Distância ao suporte" value={show(lab.distance_to_support_pct, (v) => formatMemePct(v))} />
      <Field label="Fundos ascendentes" value={yesNoLabel(lab.higher_lows)} mono={false} />
      <Field label="Rompimento 15 min" value={yesNoLabel(lab.breakout_15m)} mono={false} />
      <Field label="Hype" value={hype} />
      <Field label="Criador vendeu?" value={creator} mono={false} />
      <Field label="Progresso da curva" value={progress} />
      <Field label="Idade" value={show(lab.age_minutes, (v) => `${v} min`)} />
      <Field label="Compradores únicos" value={lab.unique_buyers === null ? "sem fita" : String(lab.unique_buyers)} />
    </>
  );
}

function LabSection({ row }: { row: MemeTestRow }) {
  const lab = row.lab_context;
  const reason = labContextReasonLabel(lab.reason);
  return (
    <Section title="O que o Lab dizia no minuto da entrada">
      <Field label="Minuto do Lab" value={show(lab.features_end_time, when)} />
      <Field label="Versão" value={lab.features_version ?? ABSENT} />
      {reason ? <div className="col-span-2 text-[13px] text-fg-muted">{reason}</div> : <LabReadings lab={lab} />}
      <Field label="Gatilhos da proposta" value={lab.gate_reasons.map(String).join(", ") || ABSENT} mono={false} />
    </Section>
  );
}

function IdentityLine({ orgSlug, row, withDetailLink }: MemeTestRowDetailProps) {
  return (
    <section className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-fg-subtle">
      <span>
        conjunto <span className="font-mono text-fg-muted">{row.rule_set.label}</span> · perna {betLegLabel(row.leg)}
        {row.parent_bet_id ? ` · sonda ${row.parent_bet_id.slice(0, 8)}` : ""}
      </span>
      {row.decided_by && <span>decidida por {row.decided_by === "rules" ? "regras" : "operador"}</span>}
      <span className="font-mono">mint {row.mint}</span>
      <Link href={`/${orgSlug}/meme/${row.mint}`} className="text-fg-muted underline">
        ver moeda
      </Link>
      {withDetailLink && row.bet_id && (
        <Link href={betDetailHref(orgSlug, row.bet_id)} className="text-fg-muted underline">
          ficha da aposta
        </Link>
      )}
    </section>
  );
}

/** Everything the dense row does not show: the two photographs in full, fees, tokens, the quote and what the Lab said in the minute of the entry. Plain component (no hooks) so the client table and the server cards share it. */
export function MemeTestRowDetail({ orgSlug, row, withDetailLink = true }: MemeTestRowDetailProps) {
  return (
    <div className="flex flex-col gap-4 text-xs">
      <EntrySection row={row} />
      <ExitSection row={row} />
      <QuoteSection row={row} />
      <LabSection row={row} />
      <IdentityLine orgSlug={orgSlug} row={row} withDetailLink={withDetailLink} />
    </div>
  );
}
