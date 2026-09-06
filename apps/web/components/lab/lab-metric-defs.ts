/**
 * Portuguese names and exact tooltip definitions for the five metrics named
 * in SHADOW-LAB.md §9 and required verbatim by brief S3b. Plain data --
 * never duplicated as a hardcoded string in a component.
 */
export const METRIC_DEFS = {
  target_rate_among_resolved_touches: {
    label: "Taxa de alvo entre toques resolvidos",
    definition: "taxa de alvo entre toques resolvidos = target/(target+stop)",
  },
  net_profit_rate: {
    label: "Taxa de lucro líquido",
    definition: "taxa de lucro líquido = encerrados avaliáveis com R_net > 0 / encerrados avaliáveis",
  },
  hypothetical_net_expectancy_r: {
    label: "Expectancy líquida hipotética (R)",
    definition: "expectancy líquida hipotética em R por entrada encerrada avaliável",
  },
  profit_factor: {
    label: "Profit factor",
    definition: "profit factor = soma de R positivos / |soma de R negativos|",
  },
  sum_of_hypothetical_r: {
    label: "Soma de R hipotéticos",
    definition: "soma de R hipotéticos, ordenada por exit_ts",
  },
} as const;

export type MetricKey = keyof typeof METRIC_DEFS;
