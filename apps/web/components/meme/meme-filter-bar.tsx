import Link from "next/link";

import type { MemeTokenSort } from "@/lib/api/meme-types";

import { MEME_TOKEN_STATES, memeTokenStateLabel } from "./labels";

const SORT_LABEL: Record<MemeTokenSort, string> = {
  mcap: "Mcap",
  age: "Idade",
  progress: "Progresso",
};

function href(orgSlug: string, state: string | null, sort: MemeTokenSort): string {
  const params = new URLSearchParams();
  if (state) params.set("state", state);
  params.set("sort", sort);
  return `/${orgSlug}/meme?${params.toString()}`;
}

function pill(active: boolean): string {
  return active ? "border-gold bg-gold-soft text-fg" : "border-border text-fg-muted hover:border-border-strong";
}

export interface MemeFilterBarProps {
  orgSlug: string;
  state: string | null;
  sort: MemeTokenSort;
}

/** Server-rendered links -- state/sort are entirely server-driven query params (`meme/page.tsx` re-fetches on navigation), no client state needed. */
export function MemeFilterBar({ orgSlug, state, sort }: MemeFilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs">
      <div className="flex items-center gap-1">
        <span className="mr-1 text-fg-muted">Estado:</span>
        <Link href={href(orgSlug, null, sort)} className={`rounded-full border px-2 py-1 ${pill(state === null)}`}>
          Todos
        </Link>
        {MEME_TOKEN_STATES.map((s) => (
          <Link key={s} href={href(orgSlug, s, sort)} className={`rounded-full border px-2 py-1 ${pill(state === s)}`}>
            {memeTokenStateLabel(s)}
          </Link>
        ))}
      </div>
      <div className="flex items-center gap-1">
        <span className="mr-1 text-fg-muted">Ordenar:</span>
        {(Object.keys(SORT_LABEL) as MemeTokenSort[]).map((s) => (
          <Link key={s} href={href(orgSlug, state, s)} className={`rounded-full border px-2 py-1 ${pill(sort === s)}`}>
            {SORT_LABEL[s]}
          </Link>
        ))}
      </div>
    </div>
  );
}
