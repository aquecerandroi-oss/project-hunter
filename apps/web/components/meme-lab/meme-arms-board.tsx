import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import type { MemeLabOut } from "@/lib/api/meme-lab-types";

import { MemeArmCard } from "./meme-arm-card";
import { sortRuleSets } from "./meme-arms-format";

export interface MemeArmsBoardProps {
  data: MemeLabOut;
}

/**
 * The meme paper Lab's scoreboard per rule set (`GET /meme/lab`, T4.6),
 * finally rendered: until this component, the endpoint's `rule_sets` array
 * was read nowhere in the web app (`lib/api/meme-desk.ts::getMemeLoopState`
 * only reads `sources.lab_last_tick_at`), so a brand-new arm like
 * `recuo_v1/1` (T4.91) existed in the database and answered on this very
 * endpoint with zero web page ever showing it. One card per rule set on
 * record, active first (`sortRuleSets`) -- data-driven off the API's own
 * list, never a hardcoded roster of arm names; a set with no bet yet still
 * gets a card, honestly empty (`MemeArmCard`).
 */
export function MemeArmsBoard({ data }: MemeArmsBoardProps) {
  const ruleSets = sortRuleSets(data.rule_sets);
  return (
    <section className="flex flex-col gap-3" aria-label="Braços de pesquisa do meme">
      <div>
        <h2 className="text-sm font-medium text-fg">Braços de pesquisa — meme</h2>
        <p className="text-xs text-fg-muted">
          Todo conjunto de regras do laço meme (pump.fun) registrado no banco, com o resultado dos últimos {data.days_limit} dias corridos — PAPEL, nenhuma transação real. Um conjunto recém-criado mostra menos dias, nunca um período inventado.
        </p>
        <p className="text-[11px] text-fg-subtle">
          Consultado em <BrasiliaInstant iso={data.as_of} />
        </p>
      </div>
      {ruleSets.length === 0 ? (
        <p className="rounded-md border border-border p-4 text-sm text-fg-muted">Nenhum conjunto de regras registrado ainda.</p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {ruleSets.map((ruleSet) => (
            <MemeArmCard key={ruleSet.id} ruleSet={ruleSet} daysLimit={data.days_limit} />
          ))}
        </ul>
      )}
    </section>
  );
}
