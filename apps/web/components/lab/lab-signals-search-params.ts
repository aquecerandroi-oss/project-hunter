/**
 * Pure parsing of `/lab`'s own `?state=&page_size=&c=` query params (T3.37)
 * -- split out of `app/(app)/[orgSlug]/lab/page.tsx` so that Server
 * Component stays under the lint config's file-size/complexity budgets and
 * this logic is independently unit-testable without rendering a page.
 */
import { DEFAULT_LAB_SIGNALS_PAGE_SIZE, LAB_SIGNALS_PAGE_SIZES, type LabSignalsPageSize, type LabSignalsState } from "@/lib/api/lab-types";

// `closed` is the web's own default (brief T3.17b item 4's decision,
// "Concluídas" first) -- the API's own default (no `state` given) is `all`.
const LAB_STATES: LabSignalsState[] = ["closed", "open", "pending", "all"];

function isLabState(value: string | undefined): value is LabSignalsState {
  return LAB_STATES.includes(value as LabSignalsState);
}

function isPageSize(value: string | undefined): boolean {
  return value !== undefined && (LAB_SIGNALS_PAGE_SIZES as readonly number[]).includes(Number(value));
}

/** Repeated `?c=` query params are the keyset cursor stack (`lab-signals-query.ts`'s own doc) -- Next.js hands a bare `searchParams` value back as `string | string[] | undefined` depending on how many times the key appears. */
function cursorPathFrom(raw: string | string[] | undefined): string[] {
  if (raw === undefined) return [];
  return Array.isArray(raw) ? raw : [raw];
}

export interface LabSignalsRawSearchParams {
  state?: string;
  page_size?: string;
  c?: string | string[];
}

export interface LabSignalsQueryParams {
  state: LabSignalsState;
  pageSize: LabSignalsPageSize;
  /** The keyset cursors used to reach this page from page 1, in visiting order -- empty means page 1. */
  cursorPath: string[];
  /** The cursor for THIS page's own request -- the last of `cursorPath`, or `undefined` on page 1. */
  cursor: string | undefined;
}

/** An unrecognized `state`/`page_size` falls back to the web's own default rather than erroring or forwarding a value the API would 422 on. */
export function parseLabSignalsQuery(sp: LabSignalsRawSearchParams): LabSignalsQueryParams {
  const state: LabSignalsState = isLabState(sp.state) ? sp.state : "closed";
  const pageSize: LabSignalsPageSize = isPageSize(sp.page_size) ? (Number(sp.page_size) as LabSignalsPageSize) : DEFAULT_LAB_SIGNALS_PAGE_SIZE;
  const cursorPath = cursorPathFrom(sp.c);
  const cursor = cursorPath.length > 0 ? cursorPath[cursorPath.length - 1] : undefined;
  return { state, pageSize, cursorPath, cursor };
}
