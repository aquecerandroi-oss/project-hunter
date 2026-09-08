/**
 * The wallet's plain-Portuguese vocabulary for every enum
 * `lib/api/portfolio-types.ts` exports (DESIGN-5, "sem backstage na copy":
 * nenhum enum cru na tela). `tests/portfolio-labels.test.ts` fails the
 * moment a new member is added to `TradeDirection`/`OrderSide`/`OrderType`/
 * `OrderPurpose`/`OrderStatus`/`ExecutionMode`/`PortfolioType`/
 * `PortfolioStatus`/`PositionStatus`/`ExitReason` without a matching entry
 * here. `killSwitchLabel` (kill switch scopes/transition) is deliberately
 * reused from `portfolio-format.ts`, not redefined here -- it is its own
 * established, ALL-CAPS-by-design vocabulary (a safety indicator), already
 * covered by `tests/portfolio-format.test.ts`.
 */
import type {
  ExecutionMode,
  ExitReason,
  OrderPurpose,
  OrderSide,
  OrderStatus,
  OrderType,
  PortfolioStatus,
  PortfolioType,
  PositionStatus,
} from "@/lib/api/portfolio-types";
import type { TradeDirectionValue } from "@/lib/api/radar-types";

/** `TradeDirection` -- `direction` on both `PositionOut` and `PortfolioTradeOut`. */
export const DIRECTION_LABEL: Record<TradeDirectionValue, string> = {
  long: "Comprado",
  short: "Vendido",
  neutral: "Neutro",
};

/** `OrderSide`. */
export const SIDE_LABEL: Record<OrderSide, string> = {
  buy: "Compra",
  sell: "Venda",
};

/** `PortfolioType`/`ExecutionMode` share the same three members (`paper`/`shadow`/`live`) -- one map, two domain-named exports. */
const MODE_LABEL: Record<"paper" | "shadow" | "live", string> = {
  paper: "Paper",
  shadow: "Sombra",
  live: "Live",
};

export const PORTFOLIO_TYPE_LABEL: Record<PortfolioType, string> = MODE_LABEL;
export const EXECUTION_MODE_LABEL: Record<ExecutionMode, string> = MODE_LABEL;

export const PORTFOLIO_STATUS_LABEL: Record<PortfolioStatus, string> = {
  active: "Ativa",
  paused: "Pausada",
  archived: "Arquivada",
};

export const POSITION_STATUS_LABEL: Record<PositionStatus, string> = {
  open: "Aberta",
  closing: "Fechando",
  closed: "Fechada",
};

export const ORDER_TYPE_LABEL: Record<OrderType, string> = {
  market: "A mercado",
  limit: "Limite",
  stop_market: "Stop a mercado",
  stop_limit: "Stop limite",
  take_profit: "Realização de lucro",
};

export const ORDER_PURPOSE_LABEL: Record<OrderPurpose, string> = {
  entry: "Entrada",
  stop: "Stop",
  target: "Alvo",
  exit: "Saída",
  reduce: "Redução",
};

export const ORDER_STATUS_LABEL: Record<OrderStatus, string> = {
  pending: "Pendente",
  submitted: "Enviada",
  partially_filled: "Parcialmente preenchida",
  filled: "Preenchida",
  cancelled: "Cancelada",
  rejected: "Rejeitada",
  expired: "Expirada",
};

/** `PortfolioTradeOut.exit_reason` -- a distinct enum from Lab's own `EXIT_REASON_LABEL` (`components/lab/lab-format.ts`, different members: `invalidation` not `invalidated`, plus `manual`/`kill_switch`/`risk_event`). */
export const PORTFOLIO_EXIT_REASON_LABEL: Record<ExitReason, string> = {
  target: "Alvo",
  stop: "Stop",
  invalidation: "Invalidação",
  manual: "Manual",
  kill_switch: "Kill switch",
  expired: "Expirou",
  risk_event: "Evento de risco",
};

/** `actor_type` on a kill-switch transition/audit row travels as a plain `string` -- only `"system"`/`"user"` are emitted today (`apps/api/hunter_api/`'s own call sites), never dropped silently for a future third value. */
const ACTOR_TYPE_LABEL: Record<string, string> = {
  system: "Sistema",
  user: "Usuário",
};

export function actorTypeLabel(actorType: string): string {
  return ACTOR_TYPE_LABEL[actorType] ?? actorType;
}

/** `FxObservationOut.source` -- also a plain `string`. Known dotted sources get a readable label; anything else is shown as-is rather than hidden. */
const FX_SOURCE_LABEL: Record<string, string> = {
  "binance.spot.ticker": "Binance spot (ticker)",
};

export function fxSourceLabel(source: string): string {
  return FX_SOURCE_LABEL[source] ?? source;
}
