"use server";

import { isApiError } from "@/lib/api-error";
import { getServerSession } from "@/lib/server/auth";

import { listMemeTokens, type ListMemeTokensParams } from "./meme";
import { MEME_LABEL, type MemeTokenList } from "./meme-types";

export interface MemeTokensActionOutcome {
  ok: boolean;
  page: MemeTokenList;
  reason?: string;
}

function emptyPage(): MemeTokenList {
  return { items: [], label: MEME_LABEL, next_cursor: null };
}

/** Server Action behind `components/meme/meme-tokens-table.tsx`'s "carregar mais" (cursor pagination). */
export async function loadMemeTokensAction(orgId: string, params: ListMemeTokensParams): Promise<MemeTokensActionOutcome> {
  const session = await getServerSession();
  if (!session) return { ok: false, page: emptyPage(), reason: "unauthenticated" };

  try {
    const page = await listMemeTokens(orgId, params);
    return { ok: true, page };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, page: emptyPage(), reason };
  }
}
