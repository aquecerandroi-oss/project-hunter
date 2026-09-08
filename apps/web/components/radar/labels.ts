/**
 * Radar's plain-Portuguese vocabulary for every enum `lib/api/radar-types.ts`
 * exports (DESIGN-5, "sem backstage na copy": nenhum enum cru na tela).
 * `tests/radar-labels.test.ts` fails the moment a new member is added to
 * `RADAR_STATUS_VALUES`/`OPPORTUNITY_STAGE_VALUES`/`MARKET_REGIME_VALUES`/
 * `ANOMALY_TYPE_VALUES` without a matching entry here.
 */
import type { AnomalyTypeValue, MarketRegimeValue, OpportunityStage, RadarStatusFilter } from "@/lib/api/radar-types";

/** `RadarStatusFilter` -- covers both `StatusChip`'s badge (a subset) and every checkbox in `radar-filters.tsx` (all nine, `IN_POSITION`/`RISK_BLOCKED` included). */
export const STATUS_LABEL: Record<RadarStatusFilter, string> = {
  NORMAL: "Normal",
  WATCHING: "Observando",
  ANOMALY: "Anomalia",
  HOT: "Quente",
  ENTRY_CANDIDATE: "Candidato a entrada",
  EXTENDED: "Esticado",
  EXPIRED: "Expirado",
  IN_POSITION: "Em posição",
  RISK_BLOCKED: "Bloqueado (risco)",
};

/** `OpportunityStage` -- `NONE` is a real classification ("não dá para saber ainda"), not a null, so it gets a label too. */
export const STAGE_LABEL: Record<OpportunityStage, string> = {
  EARLY: "Início",
  DEVELOPING: "Em desenvolvimento",
  EXTENDED: "Esticado",
  NONE: "estágio indisponível",
};

/**
 * `MarketRegimeValue` (docs/PIPELINE.md §4 -- v0 trend/volatility regimes plus
 * the v1 breadth/funding/liquidation regimes). Direct translations, not
 * reinterpretations: `BTC_BULL`/`BTC_BEAR` name BTC's own trend (the regime
 * classifier's v0 anchor), `RISK_ON`/`RISK_OFF` and the rest are v1's
 * portfolio-wide read.
 */
export const REGIME_LABEL: Record<MarketRegimeValue, string> = {
  BTC_BULL: "Alta de BTC",
  BTC_BEAR: "Baixa de BTC",
  SIDEWAYS: "Lateral",
  HIGH_VOLATILITY: "Alta volatilidade",
  LOW_VOLATILITY: "Baixa volatilidade",
  RISK_ON: "Apetite a risco",
  RISK_OFF: "Aversão a risco",
  ALT_EXPANSION: "Expansão de altcoins",
  PANIC: "Pânico",
  LIQUIDITY_CONTRACTION: "Contração de liquidez",
  UNKNOWN: "Sem classificação",
};

/** `AnomalyTypeValue` (docs/PIPELINE.md §4's MVP detector list, plus `TRADE_VELOCITY_SPIKE`/`MOMENTUM_SHIFT`). */
export const ANOMALY_TYPE_LABEL: Record<AnomalyTypeValue, string> = {
  VOLUME_SPIKE: "Pico de volume",
  PRICE_ACCELERATION: "Aceleração de preço",
  VOLATILITY_EXPANSION: "Expansão de volatilidade",
  ORDERBOOK_IMBALANCE: "Desequilíbrio do livro",
  OPEN_INTEREST_SPIKE: "Pico de interesse em aberto",
  FUNDING_ANOMALY: "Funding anômalo",
  LIQUIDATION_CLUSTER: "Cluster de liquidações",
  CROSS_EXCHANGE_DIVERGENCE: "Divergência entre exchanges",
  TRADE_VELOCITY_SPIKE: "Pico de velocidade de negociação",
  MOMENTUM_SHIFT: "Mudança de momentum",
  // Fase 2/3 (docs/PIPELINE.md §4) -- já no contrato gerado, ainda sem detector rodando.
  SOCIAL_SPIKE: "Pico de menções sociais",
  WHALE_ACTIVITY: "Atividade de baleias",
};

/** `AnomalyCountCell`'s `type` field travels as a plain `string` (built off `AnomalyTypeValue` in practice) -- never drops an unrecognized value silently. */
export function anomalyTypeLabel(type: string): string {
  return ANOMALY_TYPE_LABEL[type as AnomalyTypeValue] ?? type;
}
