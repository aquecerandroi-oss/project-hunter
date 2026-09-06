/**
 * Tab structure for `/lab` (brief S3b: "a estrutura de abas fica pronta para
 * 'Backtests' e 'Paper' depois, mas sem itens inertes: só a aba que
 * existe"). `LAB_TABS` is plain data on purpose, the same shape a future
 * "Backtests"/"Paper" entry would use -- but until that tab's API exists,
 * it is not added here at all (CLAUDE.md: no inert buttons, no "coming
 * soon"). Today the array has exactly one entry, so this renders as a
 * single active section label, never a clickable tab list with disabled
 * siblings.
 */
export interface LabTab {
  key: string;
  label: string;
}

export const LAB_TABS: readonly LabTab[] = [{ key: "sombra", label: "Sombra" }];

export function LabTabs() {
  return (
    <div role="tablist" aria-label="Abas do Lab" className="flex gap-1 border-b border-border">
      {LAB_TABS.map((tab) => (
        <div
          key={tab.key}
          role="tab"
          aria-selected="true"
          className="border-b-2 border-gold px-3 py-2 text-sm font-medium text-fg"
        >
          {tab.label}
        </div>
      ))}
    </div>
  );
}
