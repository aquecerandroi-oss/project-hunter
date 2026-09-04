import { PlannedBadge } from "@/components/layout/planned-badge";

/**
 * A static, non-interactive replica of `components/layout/nav-links.tsx`'s
 * three states (default / active / planned) using the exact same classes,
 * so this preview can't silently drift from the real sidebar without
 * someone noticing the visual diff. Kept separate from `<NavLinks>` itself
 * so this dev-only page never depends on `usePathname()`/real nav-registry
 * data.
 */
export function SidebarStatesShowcase() {
  return (
    <div className="flex max-w-xs flex-col gap-1 rounded-md border border-border bg-bg-elevated p-2">
      <div className="flex items-center gap-2 rounded-md border-l-2 border-transparent px-3 py-2 text-sm font-medium text-fg/80">
        Padrão
      </div>
      <div className="flex items-center gap-2 rounded-md border-l-2 border-gold bg-bg-overlay px-3 py-2 text-sm font-medium text-fg">
        Ativo
      </div>
      <div className="flex w-full cursor-not-allowed items-center gap-2 rounded-md border-l-2 border-transparent px-3 py-2 text-left text-sm text-fg-subtle opacity-60">
        Planejado
        <PlannedBadge milestone="M2" className="ml-auto" />
      </div>
    </div>
  );
}
