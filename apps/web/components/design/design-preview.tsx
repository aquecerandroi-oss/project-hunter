"use client";

import type { ReactNode } from "react";

import { BadgesShowcase } from "@/components/design/badges-showcase";
import { ButtonsShowcase } from "@/components/design/buttons-showcase";
import { InputsShowcase } from "@/components/design/inputs-showcase";
import { KpiCardShowcase } from "@/components/design/kpi-card-showcase";
import { SidebarStatesShowcase } from "@/components/design/sidebar-states-showcase";
import { TableShowcase } from "@/components/design/table-showcase";
import { TokenSwatches } from "@/components/design/token-swatches";
import { TypographyScale } from "@/components/design/typography-scale";
import { ThemeToggle } from "@/components/layout/theme-toggle";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-fg">{title}</h2>
      {children}
    </section>
  );
}

/**
 * docs/DESIGN.md §4 -- renders the tokens and anchor components in the
 * current theme, with a toggle. Dev tool, not a feature: app/_design/page.tsx
 * gates it out of production and it is never added to lib/nav-registry.ts.
 */
export function DesignPreview() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-5xl flex-col gap-8 bg-bg px-4 py-8 text-fg">
      <header className="flex items-center justify-between border-b border-border pb-4">
        <div>
          <h1 className="text-xl font-semibold text-gold">HUNTER -- Design Tokens</h1>
          <p className="text-sm text-fg-muted">Somente desenvolvimento -- docs/DESIGN.md. Não aparece na navegação.</p>
        </div>
        <ThemeToggle />
      </header>

      <Section title="Paleta">
        <TokenSwatches />
      </Section>

      <Section title="Tipografia">
        <TypographyScale />
      </Section>

      <Section title="Botões">
        <ButtonsShowcase />
      </Section>

      <Section title="Badges de status">
        <BadgesShowcase />
      </Section>

      <Section title="Card KPI">
        <KpiCardShowcase />
      </Section>

      <Section title="Tabela densa">
        <TableShowcase />
      </Section>

      <Section title="Inputs">
        <InputsShowcase />
      </Section>

      <Section title="Estados de item de navegação">
        <SidebarStatesShowcase />
      </Section>
    </main>
  );
}
