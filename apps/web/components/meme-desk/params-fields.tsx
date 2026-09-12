"use client";

import { Input } from "@/components/ui/input";
import type { DeskParamsFormValues } from "@/lib/api/meme-desk-form-schema";

export interface ParamsFieldsProps {
  idPrefix: string;
  values: DeskParamsFormValues;
  onChange: (values: DeskParamsFormValues) => void;
  disabled?: boolean;
}

interface FieldSpec {
  key: keyof DeskParamsFormValues;
  label: string;
  hint: string;
  inputMode: "decimal" | "numeric" | "text";
}

/** Contract §Tela: `size_sol`, `alvo (×)`, `trailing (%)`, `espera máx (s)` -- labels in Portuguese, keys as the API names them. */
const FIELDS: readonly FieldSpec[] = [
  { key: "sizeSol", label: "Tamanho (SOL)", hint: "quanto de SOL entra, com a taxa de 1,75 % já dentro", inputMode: "decimal" },
  { key: "targetX", label: "Alvo (×)", hint: "múltiplo do custo para sair com lucro; maior que 1", inputMode: "decimal" },
  { key: "trailingPct", label: "Trailing (%)", hint: "queda a partir da máxima que dispara a saída; entre 0 e 100", inputMode: "decimal" },
  { key: "maxHoldS", label: "Espera máx (s)", hint: "segundos até a saída por tempo", inputMode: "numeric" },
];

/** The four operator parameters plus a note -- shared by the approval sheet and the manual buy form. */
export function ParamsFields({ idPrefix, values, onChange, disabled = false }: ParamsFieldsProps) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {FIELDS.map((field) => {
        const id = `${idPrefix}-${field.key}`;
        return (
          <div key={field.key}>
            <label htmlFor={id} className="mb-1 block text-xs font-medium text-fg-muted">
              {field.label}
            </label>
            <Input
              id={id}
              type="text"
              inputMode={field.inputMode}
              value={values[field.key]}
              onChange={(e) => onChange({ ...values, [field.key]: e.target.value })}
              disabled={disabled}
              className="w-full font-mono tabular-nums"
            />
            <p className="mt-1 text-[11px] text-fg-subtle">{field.hint}</p>
          </div>
        );
      })}
      <div className="sm:col-span-2">
        <label htmlFor={`${idPrefix}-note`} className="mb-1 block text-xs font-medium text-fg-muted">
          Nota (opcional)
        </label>
        <Input
          id={`${idPrefix}-note`}
          type="text"
          value={values.note}
          onChange={(e) => onChange({ ...values, note: e.target.value })}
          disabled={disabled}
          placeholder="por que sim / por que este tamanho"
          className="w-full"
        />
      </div>
    </div>
  );
}
