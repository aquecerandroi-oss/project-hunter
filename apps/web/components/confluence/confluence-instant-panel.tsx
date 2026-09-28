import { formatSol } from "@/components/meme/meme-format";
import { REGIME_LABEL } from "@/components/radar/labels";
import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import { Badge } from "@/components/ui/badge";
import type { AnomalyOut } from "@/lib/api/anomalies-types";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import type { DeskOut } from "@/lib/api/market-desk-types";
import type { MarketEventOut } from "@/lib/api/market-events-types";
import type { RegimeOut } from "@/lib/api/regime-types";
import type { Candle } from "@/lib/api/types";

import { deskOrderStatusLabel, ORDER_PENDING_LABEL, spotOrderReasonLabel } from "./labels";
import {
  latestOrderStateForSignal,
  positionVigenteAtCursor,
  regimeAtCursor,
  signalVigenteAtCursor,
  windowBounds,
  type SignalOrderState,
} from "./confluence-window";
import { buildBlockBRows, buildBlockCRows, formatR } from "./confluence-timeline-rows";

export interface ConfluenceInstantPanelProps {
  cursorIso: string;
  windowMinutes: number;
  candle: Candle | null;
  signals: SignalListItemOut[];
  signalsError: string | null;
  desk: DeskOut | null;
  deskError: string | null;
  events: MarketEventOut[];
  regimeHistory: RegimeOut[];
  anomalies: AnomalyOut[];
  strategyVersionLabels: Record<string, string>;
  selectedSignalId: string | null;
  onSelectSignal: (signal: SignalListItemOut) => void;
}

function remainingLabel(cursorIso: string, expiresAt: string | null): string {
  if (expiresAt === null) return "sem prazo de expiração registrado";
  const ms = new Date(expiresAt).getTime() - new Date(cursorIso).getTime();
  if (ms <= 0) return "expirado";
  const minutes = Math.round(ms / 60_000);
  return minutes < 60 ? `expira em ${minutes} min` : `expira em ${(minutes / 60).toFixed(1)} h`;
}

/** design §4A's "linha mais valiosa da tela": the one line per signal state -- split out of `SignalRow` to keep its own complexity within the lint budget once `pending` (code review round 3) joined `refused`/`executed`/`none`. */
function SignalOrderLine({ orderState }: { orderState: SignalOrderState }) {
  if (orderState.kind === "refused") return <p className="text-red">Recusada: {spotOrderReasonLabel(orderState.order.reason)}</p>;
  if (orderState.kind === "executed") {
    return (
      <p className="text-gold">
        Execução {deskOrderStatusLabel(orderState.order.status)}
        {orderState.order.tx_signature !== null ? ` · ${orderState.order.tx_signature.slice(0, 10)}…` : ""}
      </p>
    );
  }
  if (orderState.kind === "failed") return <p className="text-red">Falhou: {spotOrderReasonLabel(orderState.order.reason)}</p>;
  if (orderState.kind === "pending") return <p className="text-fg-muted">Ordem {ORDER_PENDING_LABEL}.</p>;
  return <p className="text-fg-subtle">Sem registro de admissão ou recusa para este sinal até este instante.</p>;
}

function SignalRow({ signal, cursorIso, desk, versionLabel, selected, onSelect }: { signal: SignalListItemOut; cursorIso: string; desk: DeskOut | null; versionLabel: string; selected: boolean; onSelect: () => void }) {
  // Astra's review of T4.82 (must-fix 1): an admission/refusal received
  // *after* the cursor is knowledge from the future relative to "o que
  // estava vigente" -- cutting by `received_at <= cursorIso` before reading
  // the outcome is what keeps this block from mixing the two.
  const ordersUpToCursor = (desk?.orders ?? []).filter((order) => new Date(order.received_at).getTime() <= new Date(cursorIso).getTime());
  // Code review (round 3, must-fix 3): `latestOrderStateForSignal` now also
  // needs `cursorIso` -- an order received by the cursor but only SETTLED
  // (`spot_orders.settled_at`) strictly after it must read as "pending", not
  // as whatever its current, already-mutated `status` happens to be.
  const orderState = latestOrderStateForSignal(ordersUpToCursor, signal.signal_id, cursorIso);
  return (
    <li className={`flex flex-col gap-1 rounded-md border p-2 text-xs ${selected ? "border-gold" : "border-border"}`}>
      <button type="button" onClick={onSelect} className="flex flex-wrap items-center gap-2 text-left">
        <Badge variant={signal.direction === "short" ? "negative" : "positive"}>{signal.direction}</Badge>
        <span className="font-mono text-fg">{versionLabel}</span>
        <span className="text-fg-muted">{remainingLabel(cursorIso, signal.expires_at)}</span>
      </button>
      <p className="text-fg-muted">
        referência {signal.reference_price ?? "--"} · stop {signal.stop ?? "--"} · alvo {signal.target1 ?? "--"}
      </p>
      <SignalOrderLine orderState={orderState} />
    </li>
  );
}

/**
 * Astra's review of T4.82 (must-fix 1): both the mark and the exit used to
 * render whenever they existed at all, regardless of whether their own
 * timestamp fell before or after the cursor -- a position that only exited
 * or was only marked *after* the instant being read would still show that
 * future fact under "o que estava vigente". `DeskPositionOut.mark_at` is
 * also the *latest* mark the desk holds, never a historical one (the
 * schema's own docstring), so a mark from before the cursor is still only
 * as good as "the last thing we knew as of now", not "the mark at the
 * cursor" -- both gates below use design §5's own sentence for the case
 * where nothing reconstructable survives the cut.
 */
function PositionRow({ position, cursorIso }: { position: DeskOut["positions"][number]; cursorIso: string }) {
  const cursor = new Date(cursorIso).getTime();
  const markUpToCursor = position.mark_sol !== null && position.mark_at !== null && new Date(position.mark_at).getTime() <= cursor;
  const exitUpToCursor = position.exit_at !== null && new Date(position.exit_at).getTime() <= cursor;
  return (
    <li className="flex flex-col gap-1 rounded-md border border-border p-2 text-xs">
      <p className="text-fg">
        entrada <BrasiliaInstant iso={position.entry_at} className="font-mono" /> · gasto {(position.sol_spent_lamports / 1e9).toFixed(4)} SOL
      </p>
      {markUpToCursor ? (
        <p className="text-fg-muted">
          última marca conhecida até este instante: {formatSol(position.mark_sol as string)} (
          <BrasiliaInstant iso={position.mark_at as string} className="font-mono" />)
        </p>
      ) : (
        <p className="text-fg-subtle">estado da mesa naquele instante não reconstruível -- sem marca anterior a este instante</p>
      )}
      {exitUpToCursor && (
        <p className="text-gold">
          saída <BrasiliaInstant iso={position.exit_at as string} className="font-mono" /> · {formatR(position.r_multiple)} · {position.pnl_sol !== null ? formatSol(position.pnl_sol) : "PnL não calculado"}
        </p>
      )}
    </li>
  );
}

/** Astra's review of T4.82 (must-fix 2): `tracking_state`/`status` are the signal's/anomaly's CURRENT state, not a snapshot taken at the cursor -- there is no "state as of X" read in either API today. A signal active at 11:45 but terminal by now reads as "not vigente" here, silently. This is a real gap (named as a follow-up in the delivery report, not fixed by this diff), so the panel says so instead of implying the read is exact whenever the cursor is meaningfully in the past. */
const STALE_STATE_THRESHOLD_MS = 5 * 60_000;

function stateReconstructionCaveat(cursorIso: string): string | null {
  if (Date.now() - new Date(cursorIso).getTime() <= STALE_STATE_THRESHOLD_MS) return null;
  return 'Sinais e anomalias abaixo usam o estado ATUAL de cada um (não existe leitura "como estava neste instante" para os dois); um sinal ou anomalia que já mudou de estado desde então pode não aparecer aqui.';
}

function BlockA({ cursorIso, candle, signals, signalsError, desk, deskError, regimeHistory, anomalies, strategyVersionLabels, selectedSignalId, onSelectSignal }: Omit<ConfluenceInstantPanelProps, "windowMinutes" | "events" | "onSelectSignal"> & { onSelectSignal: (signal: SignalListItemOut) => void }) {
  const vigenteSignals = signals.filter((s) => signalVigenteAtCursor(s, cursorIso));
  const vigentePositions = desk?.positions.filter((p) => positionVigenteAtCursor(p, cursorIso)) ?? [];
  const regime = regimeAtCursor(regimeHistory, cursorIso);
  const activeAnomalies = anomalies.filter((a) => new Date(a.detected_at).getTime() <= new Date(cursorIso).getTime() && a.status === "active");
  const caveat = stateReconstructionCaveat(cursorIso);

  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">O que estava vigente</h3>
      {candle ? (
        <p className="font-mono text-sm tabular-nums text-fg">
          O {candle.open} · H {candle.high} · L {candle.low} · C {candle.close} · vol {candle.volume}
        </p>
      ) : (
        <p className="text-sm text-fg-muted">Instante fora dos candles carregados.</p>
      )}
      {caveat !== null && <p className="text-[11px] text-warning">{caveat}</p>}

      <div>
        <h4 className="mb-1 text-[11px] font-medium text-fg-muted">Sinal do Lab</h4>
        {signalsError !== null ? (
          <p className="text-sm text-red">Sinais indisponíveis: {signalsError}</p>
        ) : vigenteSignals.length === 0 ? (
          <p className="text-sm text-fg-muted">Nenhum sinal do Lab vigente neste instante.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {vigenteSignals.map((signal) => (
              <SignalRow
                key={signal.signal_id}
                signal={signal}
                cursorIso={cursorIso}
                desk={desk}
                versionLabel={strategyVersionLabels[signal.strategy_version_id] ?? "versão desconhecida"}
                selected={signal.signal_id === selectedSignalId}
                onSelect={() => onSelectSignal(signal)}
              />
            ))}
          </ul>
        )}
      </div>

      <div>
        <h4 className="mb-1 text-[11px] font-medium text-fg-muted">A nossa posição</h4>
        {deskError !== null ? (
          <p className="text-sm text-red">Mesa spot/1 indisponível: {deskError}</p>
        ) : vigentePositions.length === 0 ? (
          <p className="text-sm text-fg-muted">Nenhuma posição real spot/1 vigente neste instante.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {vigentePositions.map((position) => (
              <PositionRow key={position.id} position={position} cursorIso={cursorIso} />
            ))}
          </ul>
        )}
      </div>

      <p className="text-xs text-fg-muted">
        Regime: {regime ? `${REGIME_LABEL[regime.regime as keyof typeof REGIME_LABEL] ?? regime.regime} (global)` : "sem leitura de regime anterior a este instante"}
      </p>
      <p className="text-xs text-fg-muted">
        {activeAnomalies.length === 0 ? "sem anomalias ativas conhecidas neste instante" : `${activeAnomalies.length} anomalia(s): ${activeAnomalies.map((a) => a.type).join(", ")}`}
      </p>
    </section>
  );
}

/**
 * "Neste instante" (design §4): três blocos, nunca fundidos -- o que estava
 * vigente, o que acabou de acontecer (±N) e o que só descobrimos depois. A
 * separação é o que impede a tela de misturar conhecimento do instante com
 * conhecimento posterior.
 */
export function ConfluenceInstantPanel(props: ConfluenceInstantPanelProps) {
  const bounds = windowBounds(props.cursorIso, props.windowMinutes);
  const blockB = buildBlockBRows(props.cursorIso, bounds, props.signals, props.events, props.desk);
  const blockC = buildBlockCRows(props.cursorIso, props.signals, props.events, props.desk);

  return (
    <div className="flex flex-col gap-5 rounded-lg border border-border bg-bg-elevated p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-fg">
        Neste instante · <BrasiliaInstant iso={props.cursorIso} />
      </h2>
      <BlockA {...props} />
      <section className="flex flex-col gap-2 border-t border-border pt-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
          O que acabara de acontecer (±{props.windowMinutes} min)
        </h3>
        {blockB.length === 0 ? (
          <p className="text-sm text-fg-muted">Nada registrado nesta janela.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-xs">
            {blockB.map((row) => (
              <li key={row.key}>
                <BrasiliaInstant iso={row.iso} className="mr-1 font-mono text-fg-subtle" />
                {row.text}
              </li>
            ))}
          </ul>
        )}
      </section>
      <details className="border-t border-border pt-3">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-fg-muted">
          Depois deste instante ({blockC.length})
        </summary>
        {blockC.length === 0 ? (
          <p className="mt-2 text-sm text-fg-muted">Nada descoberto depois deste instante, até onde os dados carregados alcançam.</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-1 text-xs">
            {blockC.map((row) => (
              <li key={row.key}>
                <BrasiliaInstant iso={row.iso} className="mr-1 font-mono text-fg-subtle" />
                {row.text}
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}
