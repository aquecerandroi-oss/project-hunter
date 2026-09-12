"use client";

/**
 * "Posições reais abertas" (T4.17 deliverable 3): the real executor's own
 * open positions (`GET /meme/live`'s `positions`, `status === "open"`), each
 * with the honest mark and "Vender agora (REAL)" behind the same two-step
 * confirmation as approving REAL -- here, typing the word "VENDER" instead
 * of the size. `POST .../meme/live/positions/{id}/sell-now`: 202 even on a
 * replay, the executor sells on its next pass at the curve's price then,
 * never at the mark shown now.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { formatSol } from "@/components/meme/meme-format";
import { BrasiliaShort } from "@/components/time/brasilia-instant";
import { Button } from "@/components/ui/button";
import { computeAgeMs, formatAge } from "@/hooks/useAgeTicker";
import { sellNowLiveAction } from "@/lib/api/meme-live-actions";
import type { LivePosition } from "@/lib/api/meme-live-types";

import { liveMarkSourceLabel, realActionProblemMessage } from "./labels";
import { MAINNET_WARNING, RealBadge, WordMatchField, wordMatches } from "./real-confirm";
import { executorRefusalLabel } from "./refusal-labels";

const SELL_WORD = "VENDER";

type ConfirmStep = "idle" | "summary" | "type";

function readBlocked(exitIntent: Record<string, unknown> | null): string | null {
  if (!exitIntent) return null;
  const blocked = exitIntent.blocked;
  return typeof blocked === "string" && blocked.length > 0 ? blocked : null;
}

/** Why "Vender agora (REAL)" is off, in the order the operator would ask: role, then a request already in flight, then the position's own `can_sell_now`. `null` means the button is live. */
function sellDisabledReason(position: LivePosition, canOperate: boolean): string | null {
  if (!canOperate) return "Requer o papel Trader ou superior nesta organização.";
  if (position.sell_requested_at) return "Venda já solicitada — aguardando o executor.";
  if (!position.can_sell_now) return "Posição não está disponível para venda agora.";
  return null;
}

function PositionMetrics({ position, nowMs }: { position: LivePosition; nowMs: number }) {
  const markAge = computeAgeMs(position.mark_at, nowMs);
  return (
    <div className="grid grid-cols-2 gap-2 font-mono text-xs tabular-nums sm:grid-cols-4">
      <div>
        <p className="font-sans text-[11px] text-fg-muted">Gasto</p>
        <p className="text-fg">{formatSol(position.sol_spent)}</p>
      </div>
      <div>
        <p className="font-sans text-[11px] text-fg-muted">Marca (SOL)</p>
        <p className="text-fg">{position.mark_sol ? formatSol(position.mark_sol) : "sem marca ainda"}</p>
        <p className="font-sans text-[11px] text-fg-subtle">
          {markAge === null ? "sem fotografia ainda" : `atualizado há ${formatAge(markAge)}`}
          {liveMarkSourceLabel(position.mark_source) ? ` · ${liveMarkSourceLabel(position.mark_source)}` : ""}
        </p>
      </div>
      <div>
        <p className="font-sans text-[11px] text-fg-muted">Máxima (SOL)</p>
        <p className="text-fg">{position.high_water_sol ? formatSol(position.high_water_sol) : "—"}</p>
      </div>
      <div>
        <p className="font-sans text-[11px] text-fg-muted">Tokens</p>
        <p className="text-fg">{position.tokens.toLocaleString("pt-BR")}</p>
      </div>
    </div>
  );
}

interface SellNowRealConfirmProps {
  position: LivePosition;
  step: Extract<ConfirmStep, "summary" | "type">;
  typed: string;
  busy: boolean;
  onTypedChange: (value: string) => void;
  onContinue: () => void;
  onConfirm: () => void;
  onBack: () => void;
}

function SellNowRealConfirm({ position, step, typed, busy, onTypedChange, onContinue, onConfirm, onBack }: SellNowRealConfirmProps) {
  if (step === "summary") {
    return (
      <div className="flex flex-col gap-2 rounded-md border border-red/40 bg-red-soft/20 p-3 text-xs">
        <div className="flex items-center gap-2">
          <RealBadge />
          <span className="font-medium text-fg">{position.mint.length <= 12 ? position.mint : `${position.mint.slice(0, 5)}…${position.mint.slice(-5)}`}</span>
        </div>
        <p className="font-mono tabular-nums text-fg">
          gasto {formatSol(position.sol_spent)} · marca {position.mark_sol ? formatSol(position.mark_sol) : "sem marca ainda"}
        </p>
        <p className="font-semibold text-red">{MAINNET_WARNING} A venda sai no preço da curva na próxima passada do executor, não nesta marca.</p>
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="destructive" onClick={onContinue} disabled={busy}>
            Continuar
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={onBack} disabled={busy}>
            Cancelar
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-md border border-red/40 bg-red-soft/20 p-3 text-xs">
      <WordMatchField id={`sell-real-${position.id}`} word={SELL_WORD} label={`Digite ${SELL_WORD} para liberar o envio`} value={typed} onChange={onTypedChange} disabled={busy} />
      <div className="flex gap-2">
        <Button type="button" size="sm" variant="destructive" onClick={onConfirm} disabled={busy || !wordMatches(SELL_WORD, typed)}>
          {busy ? "Enviando..." : "Confirmar venda (REAL)"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onBack} disabled={busy}>
          Voltar
        </Button>
      </div>
    </div>
  );
}

function PositionCard({ orgSlug, orgId, position, canOperate, nowMs }: { orgSlug: string; orgId: string; position: LivePosition; canOperate: boolean; nowMs: number }) {
  const router = useRouter();
  const [step, setStep] = useState<ConfirmStep>("idle");
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const idempotencyKeyRef = useRef<string | null>(null);

  function keyFor(): string {
    if (!idempotencyKeyRef.current) idempotencyKeyRef.current = crypto.randomUUID();
    return idempotencyKeyRef.current;
  }

  async function confirm(): Promise<void> {
    setError(null);
    setBusy(true);
    try {
      const result = await sellNowLiveAction(orgId, position.id, keyFor());
      if (!result.ok) {
        setError(realActionProblemMessage(result.problem));
        return;
      }
      idempotencyKeyRef.current = null;
      setStep("idle");
      setTyped("");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  const blocked = readBlocked(position.exit_intent as Record<string, unknown> | null);
  const disabledReason = sellDisabledReason(position, canOperate);

  return (
    <li className="flex flex-col gap-2 rounded-md border border-red/30 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Link href={`/${orgSlug}/meme/${position.mint}`} className="text-sm font-medium text-fg hover:underline">
          {position.mint.length <= 12 ? position.mint : `${position.mint.slice(0, 5)}…${position.mint.slice(-5)}`}
        </Link>
        <span className="text-[11px] text-fg-subtle">
          entrada <BrasiliaShort iso={position.entry_at} />
        </span>
      </div>
      <PositionMetrics position={position} nowMs={nowMs} />
      {blocked && <p className="text-[11px] font-medium text-warning">saída bloqueada: {executorRefusalLabel(blocked)}</p>}
      {position.sell_requested_at && (
        <p className="text-[11px] text-fg-muted">
          venda solicitada em <BrasiliaShort iso={position.sell_requested_at} /> por {position.sell_requested_by ?? "operador"}
        </p>
      )}
      {error && <p className="text-xs text-red">{error}</p>}
      {step === "idle" ? (
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" variant="destructive" onClick={() => setStep("summary")} disabled={disabledReason !== null} title={disabledReason ?? undefined}>
            Vender agora (REAL)
          </Button>
          {disabledReason && <span className="text-[11px] text-fg-subtle">{disabledReason}</span>}
        </div>
      ) : (
        <SellNowRealConfirm
          position={position}
          step={step === "type" ? "type" : "summary"}
          typed={typed}
          busy={busy}
          onTypedChange={setTyped}
          onContinue={() => setStep("type")}
          onConfirm={() => void confirm()}
          onBack={() => {
            setStep("idle");
            setTyped("");
            setError(null);
          }}
        />
      )}
    </li>
  );
}

export interface LivePositionsSectionProps {
  orgSlug: string;
  orgId: string;
  positions: LivePosition[];
  canOperate: boolean;
  nowMs: number;
}

/** Only `status === "open"` real positions -- the panel above already shows `positions_open` as a count; this is the operable list. */
export function LivePositionsSection({ orgSlug, orgId, positions, canOperate, nowMs }: LivePositionsSectionProps) {
  const open = positions.filter((p) => p.status === "open");
  return (
    <section className="flex flex-col gap-3">
      <h2 className="flex items-center gap-2 text-sm font-medium text-fg">
        <RealBadge /> Posições reais abertas
      </h2>
      {open.length === 0 ? (
        <p className="rounded-md border border-border p-4 text-sm text-fg-muted">Nenhuma posição real aberta agora.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {open.map((position) => (
            <PositionCard key={position.id} orgSlug={orgSlug} orgId={orgId} position={position} canOperate={canOperate} nowMs={nowMs} />
          ))}
        </ul>
      )}
    </section>
  );
}
