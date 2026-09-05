"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { MARKET_SEARCH_MIN_LENGTH, useMarketSearch } from "@/hooks/useMarketSearch";
import type { MarketSearchResult } from "@/lib/api/markets-actions";
import { cn } from "@/lib/utils";

export interface CommandPaletteProps {
  orgSlug: string;
}

const RESULT_LIMIT_HINT = 8;

function resultId(result: MarketSearchResult): string {
  return `command-result-${result.exchange}-${result.symbol}`;
}

/**
 * Command palette (T1.5b joint decision #7): a visible "Buscar mercados"
 * button (never a shortcut-only, undiscoverable feature) plus Ctrl/⌘K, real
 * server-side search over the monitored universe (never a client-side
 * filter of whatever page happened to load), results showing exchange, full
 * keyboard navigation. The copy says explicitly that this searches the
 * *monitored* universe, not "every market that ever existed" -- joint
 * decision #7: "deixar claro que busca só o carregado (ou ligar ao q= da
 * API); totais globais não viram filtros locais sem dizer isso". This is
 * wired to the real `q=` param (`lib/api/markets-actions.ts`), so it is a
 * true (bounded) global search, not the markets table's own "only this
 * page" caveat.
 */
export function CommandPalette({ orgSlug }: CommandPaletteProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function handleShortcut(event: globalThis.KeyboardEvent): void {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  return (
    <>
      {/*
       * The label + shortcut hint collapse to an icon-only button below
       * `sm` (T1.5b Astra must-fix #7: an already-crowded, non-wrapping
       * topbar has no room for the full label on a narrow phone) -- the
       * accessible name stays "Buscar mercados" either way via `aria-label`,
       * so a screen reader user never loses it.
       */}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        aria-label="Buscar mercados"
        className="gap-2 text-fg-muted"
      >
        <Search className="size-4" aria-hidden="true" />
        <span className="hidden sm:inline">Buscar mercados</span>
        <kbd className="ml-1 hidden rounded border border-border-strong px-1 text-[10px] font-normal text-fg-subtle sm:inline">
          Ctrl K
        </kbd>
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogTitle className="sr-only">Buscar mercados</DialogTitle>
          {/*
           * Mounted only while open -- a fresh `CommandPaletteBody` instance
           * per open means its query/results/status state starts clean with
           * no "reset on open" effect (and the setState-during-render or
           * setState-in-effect anti-patterns that would come with one).
           */}
          {open && <CommandPaletteBody orgSlug={orgSlug} onNavigate={() => setOpen(false)} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

interface CommandPaletteBodyProps {
  orgSlug: string;
  onNavigate: () => void;
}

function CommandPaletteBody({ orgSlug, onNavigate }: CommandPaletteBodyProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  // The debounced, race-safe search itself lives in `hooks/useMarketSearch.ts`
  // (M9: kept this component under the lint config's per-function complexity
  // budget, and that logic is independently unit-testable) -- also where the
  // minimum-query-length floor (M8, security) is enforced.
  const { status, results: visibleResults } = useMarketSearch(query);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Resets the highlighted result whenever the actual set of results
  // changes (a fresh response landed, or the query changed enough to clear
  // them) -- keyed on a stable string, not the `results` array reference
  // itself (`useMarketSearch` can return a brand-new `[]` on renders where
  // nothing actually changed).
  const resultsKey = visibleResults.map((result) => `${result.exchange}:${result.symbol}`).join("|");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing the highlighted index to a derived, external (hook) result set
    setActiveIndex(0);
  }, [resultsKey]);

  const trimmedQuery = query.trim();
  // Below `MARKET_SEARCH_MIN_LENGTH` the hook never searches at all (M8) --
  // this is distinct from "searched and found nothing", so the "Nenhum
  // mercado encontrado" message must not appear for a too-short query.
  const isEmpty = trimmedQuery.length < MARKET_SEARCH_MIN_LENGTH;

  function openResult(result: MarketSearchResult | undefined): void {
    if (!result) return;
    onNavigate();
    router.push(`/${orgSlug}/markets/${encodeURIComponent(result.exchange)}/${encodeURIComponent(result.symbol)}`);
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((prev) => Math.min(visibleResults.length - 1, prev + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((prev) => Math.max(0, prev - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      openResult(visibleResults[activeIndex]);
    }
  }

  return (
    <>
      <div className="border-b border-border p-3">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleInputKeyDown}
          placeholder="Símbolo (ex.: BTCUSDT)"
          // Deliberately distinct from the Dialog's own accessible name
          // ("Buscar mercados", carried by `DialogTitle` via Radix's
          // auto-wired `aria-labelledby`) -- otherwise two elements (the
          // dialog and this input) would share one accessible name and
          // `getByLabelText`/assistive tech could not tell them apart.
          aria-label="Buscar por símbolo"
          role="combobox"
          aria-expanded={visibleResults.length > 0}
          aria-controls="command-palette-results"
          aria-activedescendant={visibleResults[activeIndex] ? resultId(visibleResults[activeIndex]) : undefined}
          // `outline-none` only removes the default outline's shape/offset --
          // `focus-visible:ring-2 focus-visible:ring-gold` replaces it with
          // the app's own visible focus treatment (T1.5b Astra must-fix #6:
          // this used to remove the outline and never provide the
          // replacement, leaving keyboard focus invisible).
          className="w-full rounded bg-transparent text-sm text-fg outline-none placeholder:text-fg-subtle focus-visible:ring-2 focus-visible:ring-gold"
        />
      </div>
      <p className="border-b border-border px-3 py-1.5 text-[11px] text-fg-subtle">
        Busca no universo monitorado (até {RESULT_LIMIT_HINT} resultados).
      </p>
      <ul id="command-palette-results" role="listbox" aria-label="Resultados" className="max-h-72 overflow-y-auto p-1">
        {!isEmpty && status === "loading" && <li className="px-3 py-2 text-sm text-fg-muted">Buscando...</li>}
        {!isEmpty && status === "error" && (
          <li className="px-3 py-2 text-sm text-red">Busca indisponível no momento. Tente novamente.</li>
        )}
        {!isEmpty && status === "idle" && visibleResults.length === 0 && (
          <li className="px-3 py-2 text-sm text-fg-muted">Nenhum mercado encontrado para &quot;{query}&quot;.</li>
        )}
        {visibleResults.map((result, index) => (
          <li key={`${result.exchange}:${result.symbol}`} id={resultId(result)} role="option" aria-selected={index === activeIndex}>
            <button
              type="button"
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => openResult(result)}
              className={cn(
                "flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm",
                index === activeIndex ? "bg-gold-soft text-fg" : "text-fg hover:bg-bg-overlay",
              )}
            >
              <span className="font-medium">{result.symbol}</span>
              {/*
               * `fg-muted` (not `fg-subtle`): the exchange code is real
               * information (which venue this result is on), and the
               * selected row's own background switches to `gold-soft`,
               * where `fg-subtle` measures below AA (T1.5b Astra must-fix
               * #6) -- `fg-muted` clears 4.5:1 on every background this app
               * uses it against.
               */}
              <span className="text-xs text-fg-muted">{result.exchange}</span>
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
