import { Input } from "@/components/ui/input";
import type { StopValidation } from "@/lib/api/manual-order-form-schema";
import { formatPct } from "@/lib/format";

export interface ManualOrderStopFieldProps {
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  check: StopValidation;
  maxStopDistancePct: string | null;
}

/**
 * The stop input plus its live distance-vs-cap hint, extracted out of
 * `manual-order-form.tsx` (kept that component under the lint config's
 * per-function complexity budget). See `validateStopAgainstMarket`'s own
 * docstring for why the cap check here is informational, never blocking.
 */
export function ManualOrderStopField({ value, onChange, disabled, check, maxStopDistancePct }: ManualOrderStopFieldProps) {
  const dirty = value.trim() !== "";
  return (
    <div>
      <label htmlFor="manual-order-stop" className="mb-1 block text-xs font-medium text-fg-muted">
        Stop
      </label>
      <Input
        id="manual-order-stop"
        type="text"
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Ex.: 64000.00"
        disabled={disabled}
        className="w-full"
      />
      {dirty && check.distancePct !== null && (
        <p className={`mt-1 text-[11px] ${check.overCap ? "text-warning" : "text-fg-subtle"}`}>
          Distância implícita: {formatPct(check.distancePct, { signed: false })}
          {maxStopDistancePct !== null && ` (teto do perfil: ${formatPct(maxStopDistancePct, { signed: false })})`}
          {check.overCap && " -- acima do teto; o motor deve recusar por distância de stop"}
        </p>
      )}
      {dirty && !check.ok && <p className="mt-1 text-[11px] text-red">{check.message}</p>}
    </div>
  );
}
