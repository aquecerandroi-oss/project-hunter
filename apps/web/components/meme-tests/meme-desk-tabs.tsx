import Link from "next/link";

export type MemeDeskTab = "mesa" | "testes";

export interface MemeDeskTabsProps {
  orgSlug: string;
  active: MemeDeskTab;
}

const TABS: readonly { key: MemeDeskTab; label: string; href: (orgSlug: string) => string }[] = [
  { key: "mesa", label: "Mesa", href: (orgSlug) => `/${orgSlug}/meme/mesa` },
  { key: "testes", label: "Testes", href: (orgSlug) => `/${orgSlug}/meme/mesa?tab=testes` },
];

/**
 * "Mesa · Testes" (brief T4.13 §2): two real `<Link>`s, never a button with
 * `router.push` (the Lab's T3.51 lesson -- an `<a href>` degrades to a full
 * navigation and the URL stays the only source of truth for the active tab).
 * `/meme/testes` renders the same "Testes" content on its own route; the tab
 * here points at `/meme/mesa?tab=testes` so the operator never leaves the desk.
 */
export function MemeDeskTabs({ orgSlug, active }: MemeDeskTabsProps) {
  return (
    <nav aria-label="Seções da mesa" className="flex gap-1 border-b border-border text-sm">
      {TABS.map((tab) => {
        const selected = tab.key === active;
        return (
          <Link
            key={tab.key}
            href={tab.href(orgSlug)}
            aria-current={selected ? "page" : undefined}
            className={
              selected
                ? "-mb-px border-b-2 border-gold px-3 py-2 font-medium text-fg"
                : "-mb-px border-b-2 border-transparent px-3 py-2 text-fg-muted hover:text-fg"
            }
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
