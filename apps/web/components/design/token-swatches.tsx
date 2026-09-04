"use client";

import { useEffect, useState } from "react";

import { AA_NORMAL_TEXT, contrastRatio, readColorToken } from "@/components/design/contrast";

interface SwatchDef {
  name: string;
  /** When set, shows a "vs <against>" contrast ratio against that other token's resolved color. */
  against?: string;
}

const BACKGROUND_TOKENS: SwatchDef[] = [{ name: "bg" }, { name: "bg-elevated" }, { name: "bg-overlay" }];
const BORDER_TOKENS: SwatchDef[] = [{ name: "border" }, { name: "border-strong" }];
const TEXT_TOKENS: SwatchDef[] = [
  { name: "fg", against: "bg" },
  { name: "fg-muted", against: "bg" },
  { name: "fg-subtle", against: "bg" },
];
const BRAND_TOKENS: SwatchDef[] = [
  { name: "gold", against: "bg" },
  { name: "gold-strong", against: "bg" },
  { name: "gold-soft" },
  { name: "gold-fg", against: "gold" },
];
const SEMANTIC_TOKENS: SwatchDef[] = [
  { name: "green", against: "bg" },
  { name: "green-soft" },
  { name: "red", against: "bg" },
  { name: "red-soft" },
  { name: "warning", against: "bg" },
  { name: "info", against: "bg" },
];

function useResolvedTokens(names: string[]): Record<string, string> {
  const [values, setValues] = useState<Record<string, string>>({});

  useEffect(() => {
    function read(): void {
      const next: Record<string, string> = {};
      for (const name of names) next[name] = readColorToken(name);
      setValues(next);
    }
    read();
    // Re-read whenever `data-theme` flips (ThemeToggle sets it on <html>).
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `names` is a module-level constant array per call site, stable across renders
  }, []);

  return values;
}

function Swatch({ def, values }: { def: SwatchDef; values: Record<string, string> }) {
  const hex = values[def.name];
  const against = def.against ? values[def.against] : undefined;
  const ratio = hex && against ? contrastRatio(hex, against) : null;
  const passes = ratio !== null && ratio >= AA_NORMAL_TEXT;

  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border p-3">
      <div className="h-12 rounded border border-border" style={{ backgroundColor: `var(--color-${def.name})` }} />
      <span className="text-[13px] font-medium text-fg">--color-{def.name}</span>
      <span className="num text-xs text-fg-muted">{hex ?? "..."}</span>
      {ratio !== null && (
        <span className={`text-xs ${passes ? "text-green" : "text-red"}`}>
          {ratio.toFixed(2)}:1 vs {def.against} -- {passes ? "AA OK" : "AA FALHA"}
        </span>
      )}
    </div>
  );
}

function SwatchGroup({ title, defs, values }: { title: string; defs: SwatchDef[]; values: Record<string, string> }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-xs font-medium uppercase tracking-wide text-fg-muted">{title}</h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {defs.map((def) => (
          <Swatch key={def.name} def={def} values={values} />
        ))}
      </div>
    </div>
  );
}

/** All docs/DESIGN.md §1 tokens, resolved live off `document.documentElement` so the shown hex always matches the active theme. */
export function TokenSwatches() {
  const allDefs = [...BACKGROUND_TOKENS, ...BORDER_TOKENS, ...TEXT_TOKENS, ...BRAND_TOKENS, ...SEMANTIC_TOKENS];
  const values = useResolvedTokens(allDefs.map((d) => d.name));

  return (
    <div className="flex flex-col gap-6">
      <SwatchGroup title="Fundos" defs={BACKGROUND_TOKENS} values={values} />
      <SwatchGroup title="Bordas" defs={BORDER_TOKENS} values={values} />
      <SwatchGroup title="Texto" defs={TEXT_TOKENS} values={values} />
      <SwatchGroup title="Marca (dourado)" defs={BRAND_TOKENS} values={values} />
      <SwatchGroup title="Semânticas" defs={SEMANTIC_TOKENS} values={values} />
    </div>
  );
}
