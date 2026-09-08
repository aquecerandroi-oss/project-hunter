import { Checkbox } from "@/components/ui/checkbox";
import { contrastRatio } from "@/components/design/contrast";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

/**
 * `ui/input.tsx`/`ui/select.tsx`/`ui/checkbox.tsx` (T3.24a's brief §2, fixes
 * C7/X6): `border-input` against the two surfaces a field can sit on
 * (`bg-overlay`, the card behind it, and `bg`, the field's own fill) -- both
 * need to clear WCAG 1.4.11's >= 3:1 for a UI component's own boundary.
 * Hex values mirror `app/globals.css`; see `badges-showcase.tsx`'s own
 * comment for why both themes are computed at once.
 */
const BORDER_INPUT_ON_OVERLAY: [string, string] = ["#666666", "#161616"];
const BORDER_INPUT_ON_OVERLAY_LIGHT: [string, string] = ["#8a8a8a", "#f3f3f3"];
const BORDER_INPUT_ON_BG: [string, string] = ["#666666", "#0a0a0a"];
const BORDER_INPUT_ON_BG_LIGHT: [string, string] = ["#8a8a8a", "#ffffff"];

function BorderInputRatios() {
  return (
    <span className="font-mono text-xs text-fg-muted">
      escuro {contrastRatio(...BORDER_INPUT_ON_OVERLAY)?.toFixed(2)}:1 (sobre card) / {contrastRatio(...BORDER_INPUT_ON_BG)?.toFixed(2)}:1
      (próprio fundo) · claro {contrastRatio(...BORDER_INPUT_ON_OVERLAY_LIGHT)?.toFixed(2)}:1 / {contrastRatio(...BORDER_INPUT_ON_BG_LIGHT)?.toFixed(2)}:1
    </span>
  );
}

/** Form inputs: gold focus ring (docs/DESIGN.md §2, "anel de foco"), `red` for validation errors, `border-input` for the field's own outline. */
export function InputsShowcase() {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-4">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-fg">Campo normal (foco: Tab)</span>
          <Input placeholder="Acme Capital" className="px-3 py-2" />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-fg">Select</span>
          <Select defaultValue="a" className="px-3 py-2">
            <option value="a">Opção A</option>
            <option value="b">Opção B</option>
          </Select>
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-fg">Checkbox</span>
          <Checkbox defaultChecked aria-label="Exemplo de checkbox" />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-fg">Campo inválido</span>
          <Input defaultValue="abc" className="border-red px-3 py-2" />
          <span className="text-xs text-red">Use um número válido</span>
        </label>
      </div>
      <BorderInputRatios />
    </div>
  );
}
