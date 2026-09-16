// Fonte única de dados demonstrativos do Hunter. Tudo aqui é DEMONSTRAÇÃO
// (identificado na interface). Números derivados (patrimônio, PnL, exposição,
// risco agregado) são CALCULADOS a partir de posições/trades — nunca digitados.

export const LIMITS = {
  initialBRL: 100000,
  fxBRLUSDT: 5.42, // referência: Binance spot USDT/BRL (ticker), registrada na abertura
  riskPerTrade: 0.0025,
  riskAggMax: 0.01,
  exposureMax: 0.40,
  exposurePerCoinMax: 0.10,
  maxPositions: 5,
  minVolume24hUSDT: 50_000_000,
  feeRate: 0.001, // taker 0,10%
  slippageBps: 5, // 0,05% estimado
};

export const ROLES = ["Proprietário", "Administrador", "Gestor", "Analista", "Operador", "Visualizador"];
// matriz de permissões (demonstrativa; a autoridade real é a API)
export const PERMS = {
  "ver": ROLES,
  "operar_paper": ["Proprietário", "Administrador", "Operador"],
  "kill_switch": ["Proprietário", "Administrador", "Gestor", "Operador"],
  "editar_lab": ["Proprietário", "Administrador", "Gestor", "Analista"],
  "crm_editar": ["Proprietário", "Administrador", "Gestor", "Operador", "Analista"],
  "admin_org": ["Proprietário", "Administrador"],
  "assinatura": ["Proprietário"],
};
export const can = (role, perm) => (PERMS[perm] || []).includes(role);

const T0 = new Date("2026-09-15T14:32:00-03:00").getTime();
const ago = (min) => new Date(T0 - min * 60000).toISOString();

export const MARKETS = [
  { sym: "BTCUSDT", ex: "Binance", price: 118432.5, chg: 1.84, vol: 18_420_000_000, liq: "alta", volat: 2.1, spread: 0.4, anomalies: 1, updated: ago(0.1), quality: "ok", regime: "Alta de BTC" },
  { sym: "ETHUSDT", ex: "Binance", price: 4482.1, chg: 2.62, vol: 9_870_000_000, liq: "alta", volat: 3.4, spread: 0.6, anomalies: 2, updated: ago(0.1), quality: "ok", regime: "Expansão de altcoins" },
  { sym: "SOLUSDT", ex: "Bybit", price: 241.87, chg: 5.91, vol: 3_120_000_000, liq: "alta", volat: 5.8, spread: 1.1, anomalies: 3, updated: ago(0.2), quality: "ok", regime: "Expansão de altcoins" },
  { sym: "BNBUSDT", ex: "Binance", price: 892.4, chg: -0.42, vol: 1_640_000_000, liq: "alta", volat: 1.9, spread: 0.8, anomalies: 0, updated: ago(0.1), quality: "ok", regime: "Lateral" },
  { sym: "XRPUSDT", ex: "Binance", price: 3.0412, chg: -1.13, vol: 2_210_000_000, liq: "alta", volat: 3.0, spread: 0.9, anomalies: 0, updated: ago(0.1), quality: "ok", regime: "Lateral" },
  { sym: "LINKUSDT", ex: "Bybit", price: 24.61, chg: 7.35, vol: 612_000_000, liq: "média", volat: 6.2, spread: 2.3, anomalies: 2, updated: ago(0.3), quality: "ok", regime: "Expansão de altcoins" },
  { sym: "AVAXUSDT", ex: "Binance", price: 31.28, chg: 3.12, vol: 388_000_000, liq: "média", volat: 5.1, spread: 2.8, anomalies: 1, updated: ago(0.2), quality: "ok", regime: "Expansão de altcoins" },
  { sym: "ARBUSDT", ex: "Bybit", price: 0.6124, chg: 9.8, vol: 142_000_000, liq: "média", volat: 8.9, spread: 4.5, anomalies: 2, updated: ago(6), quality: "atrasado", regime: "Alta volatilidade" },
  { sym: "INJUSDT", ex: "Binance", price: 14.02, chg: 12.4, vol: 38_500_000, liq: "baixa", volat: 11.2, spread: 7.9, anomalies: 3, updated: ago(0.4), quality: "ok", regime: "Alta volatilidade" },
  { sym: "PEPEUSDT", ex: "Bybit", price: 0.00001218, chg: 16.7, vol: 27_900_000, liq: "baixa", volat: 14.6, spread: 12.0, anomalies: 2, updated: ago(0.5), quality: "ok", regime: "Alta volatilidade" },
  { sym: "DOTUSDT", ex: "Binance", price: 4.71, chg: 0.31, vol: 214_000_000, liq: "média", volat: 3.3, spread: 3.1, anomalies: 0, updated: ago(42), quality: "gap", regime: "Sem classificação" },
  { sym: "ATOMUSDT", ex: "Bybit", price: 5.38, chg: -2.05, vol: 96_000_000, liq: "média", volat: 4.0, spread: 3.7, anomalies: 0, updated: ago(0.3), quality: "ok", regime: "Lateral" },
];

export const AGENTS = [
  { id: "momentum", name: "Momentum", state: "conectado", last: ago(1), markets: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "AVAXUSDT"], latencyMs: 180, dataOk: true, desc: "Mede aceleração de preço e persistência de tendência em 15m/1h. Sinal quando retorno 1h > 1,5σ e volume confirma." },
  { id: "volume", name: "Volume Anomaly", state: "conectado", last: ago(0.5), markets: ["SOLUSDT", "LINKUSDT", "ARBUSDT", "INJUSDT", "PEPEUSDT"], latencyMs: 240, dataOk: true, desc: "Detecta picos de volume relativo (z-score > 3 contra média de 7 dias)." },
  { id: "breakout", name: "Breakout", state: "simulado", last: ago(3), markets: ["ETHUSDT", "SOLUSDT", "AVAXUSDT"], latencyMs: 0, dataOk: true, desc: "Rompimento de máximas de 20 períodos com fechamento acima. Em demonstração: sinais gerados por regras sobre dados capturados." },
  { id: "orderflow", name: "Order Flow", state: "pausado", last: ago(190), markets: ["BTCUSDT", "ETHUSDT"], latencyMs: 0, dataOk: false, desc: "Desequilíbrio do livro (OFI) e agressão taker. Pausado: feed de livro da Bybit sem dados há 3 h." },
  { id: "derivatives", name: "Derivatives", state: "simulado", last: ago(2), markets: ["BTCUSDT", "ETHUSDT", "SOLUSDT"], latencyMs: 0, dataOk: true, desc: "Contexto de funding e interesse em aberto. Somente contexto analítico — não habilita operações com derivativos." },
  { id: "social", name: "Sentimento social", state: "não implementado", last: null, markets: [], latencyMs: 0, dataOk: false, desc: "Planejado para a Fase 2. Nenhum sinal é produzido." },
];

export const STAGES = [
  { id: "detectada", label: "Detectada" },
  { id: "analise", label: "Em análise" },
  { id: "validada", label: "Validada" },
  { id: "risco", label: "Avaliada pelo risco" },
  { id: "aprovada", label: "Aprovada para paper" },
  { id: "posicao", label: "Em posição" },
  { id: "encerrada", label: "Encerrada" },
];
export const SIDE_STAGES = [
  { id: "rejeitada", label: "Rejeitada" },
  { id: "expirada", label: "Expirada" },
  { id: "shadow", label: "Shadow" },
];
export const STAGE_LABEL = Object.fromEntries([...STAGES, ...SIDE_STAGES].map((s) => [s.id, s.label]));

function opp(id, sym, strategy, agents, stage, score, detected, extra = {}) {
  return {
    id, sym, strategy, agents, stage, score, detected,
    // composição do score: pesos fixos, explicados na tela. Não é probabilidade de lucro.
    scoreParts: extra.scoreParts || { anomalia: 30, contexto: 20, liquidez: 25, assimetria: 25 },
    evidence: extra.evidence || [],
    entry: extra.entry || null, invalidation: extra.invalidation || null, target: extra.target || null,
    riskStatus: extra.riskStatus || "pendente",
    riskLog: extra.riskLog || null,
    direction: "Comprado",
    env: extra.env || "paper",
    note: extra.note || "",
  };
}

const OPPS_ALFA = [
  opp("OP-1041", "SOLUSDT", "Momentum + Volume", ["momentum", "volume", "breakout"], "posicao", 78, ago(142), {
    scoreParts: { anomalia: 26, contexto: 16, liquidez: 22, assimetria: 14 },
    evidence: ["Retorno 1h +3,1% (2,4σ)", "Volume relativo z=3,8 (Volume Anomaly)", "Rompeu máxima de 20 períodos em 1h (Breakout, simulado)", "Regime: Expansão de altcoins"],
    entry: 236.4, invalidation: 229.8, target: 249.5, riskStatus: "aprovado",
  }),
  opp("OP-1044", "LINKUSDT", "Volume Anomaly", ["volume", "momentum"], "posicao", 71, ago(98), {
    scoreParts: { anomalia: 28, contexto: 12, liquidez: 17, assimetria: 14 },
    evidence: ["Volume relativo z=4,2", "Retorno 1h +2,2%", "Liquidez média: spread 2,3 bps"],
    entry: 23.9, invalidation: 23.1, target: 25.6, riskStatus: "aprovado",
  }),
  opp("OP-1049", "ETHUSDT", "Momentum", ["momentum", "derivatives"], "validada", 74, ago(21), {
    scoreParts: { anomalia: 22, contexto: 18, liquidez: 25, assimetria: 9 },
    evidence: ["Retorno 1h +1,9% (1,7σ)", "Funding neutro (Derivatives, contexto)", "Liquidez alta: 9,87 bi USDT/24h"],
    entry: 4482.1, invalidation: 4398.0, target: 4650.0,
  }),
  opp("OP-1050", "AVAXUSDT", "Breakout", ["breakout", "momentum"], "analise", 63, ago(12), {
    scoreParts: { anomalia: 18, contexto: 16, liquidez: 17, assimetria: 12 },
    evidence: ["Rompimento de 20 períodos (simulado)", "Volume relativo z=2,1 — abaixo do limiar de 3"],
    entry: 31.28, invalidation: 30.1, target: 33.6,
  }),
  opp("OP-1051", "ARBUSDT", "Volume Anomaly", ["volume"], "detectada", 58, ago(4), {
    scoreParts: { anomalia: 27, contexto: 8, liquidez: 12, assimetria: 11 },
    evidence: ["Volume relativo z=5,1", "Dados atrasados há 6 min — qualidade rebaixada"],
    entry: 0.6124, invalidation: 0.582, target: 0.672,
  }),
  opp("OP-1038", "INJUSDT", "Volume Anomaly", ["volume", "momentum"], "shadow", 69, ago(310), {
    scoreParts: { anomalia: 30, contexto: 14, liquidez: 6, assimetria: 19 },
    evidence: ["Volume relativo z=4,9", "Volume 24h 38,5 mi USDT < 50 mi (inelegível)"],
    entry: 12.9, invalidation: 12.2, target: 14.8, env: "shadow", riskStatus: "rejeitado",
    riskLog: { at: ago(305), result: "rejeitado", checks: [
      { name: "Volume 24h elegível", value: "38,5 mi USDT", limit: "≥ 50 mi USDT", ok: false },
      { name: "Exposição total", value: "18,4%", limit: "≤ 40%", ok: true },
      { name: "Exposição na moeda", value: "0%", limit: "≤ 10%", ok: true },
      { name: "Risco agregado", value: "0,50%", limit: "≤ 1,00%", ok: true },
      { name: "Posições simultâneas", value: "2", limit: "≤ 5", ok: true },
      { name: "Qualidade dos dados", value: "ok", limit: "ok", ok: true },
    ], reason: "Volume 24h abaixo do mínimo elegível. Sinal encaminhado para shadow." },
  }),
  opp("OP-1036", "PEPEUSDT", "Volume Anomaly", ["volume"], "rejeitada", 61, ago(420), {
    scoreParts: { anomalia: 29, contexto: 6, liquidez: 4, assimetria: 22 },
    evidence: ["Volume 24h 27,9 mi USDT < 50 mi", "Spread 12 bps"],
    entry: 0.0000104, invalidation: 0.0000097, riskStatus: "rejeitado",
    riskLog: { at: ago(418), result: "rejeitado", checks: [
      { name: "Volume 24h elegível", value: "27,9 mi USDT", limit: "≥ 50 mi USDT", ok: false },
      { name: "Liquidez (spread)", value: "12,0 bps", limit: "≤ 8 bps", ok: false },
      { name: "Exposição total", value: "18,4%", limit: "≤ 40%", ok: true },
      { name: "Exposição na moeda", value: "0%", limit: "≤ 10%", ok: true },
      { name: "Risco agregado", value: "0,50%", limit: "≤ 1,00%", ok: true },
      { name: "Posições simultâneas", value: "2", limit: "≤ 5", ok: true },
    ], reason: "Dois critérios falharam: volume e spread. Não encaminhado para shadow (liquidez insuficiente para acompanhar)." },
  }),
  opp("OP-1029", "XRPUSDT", "Momentum", ["momentum"], "expirada", 55, ago(1500), {
    evidence: ["Sinal perdeu força antes da validação (retorno 1h voltou a 0,3%)"], entry: 3.12, invalidation: 3.02,
  }),
  opp("OP-1018", "BTCUSDT", "Momentum", ["momentum", "derivatives"], "encerrada", 72, ago(4300), {
    evidence: ["Retorno 1h +1,6%", "Funding positivo moderado (contexto)"], entry: 114800, invalidation: 112900, target: 118400, riskStatus: "aprovado",
  }),
  opp("OP-1011", "ETHUSDT", "Breakout", ["breakout"], "encerrada", 66, ago(6900), {
    evidence: ["Rompimento 20 períodos (simulado)"], entry: 4310, invalidation: 4240, target: 4460, riskStatus: "aprovado",
  }),
];

const OPPS_LABS = [
  opp("OP-2007", "ETHUSDT", "Momentum", ["momentum"], "posicao", 70, ago(200), {
    evidence: ["Retorno 1h +1,9%", "Liquidez alta"], entry: 4401.0, invalidation: 4320.0, target: 4580.0, riskStatus: "aprovado",
  }),
  opp("OP-2009", "SOLUSDT", "Volume Anomaly", ["volume", "breakout"], "risco", 75, ago(9), {
    evidence: ["Volume relativo z=3,8", "Rompimento (simulado)"], entry: 241.87, invalidation: 234.0, target: 256.0,
  }),
  opp("OP-2010", "LINKUSDT", "Momentum", ["momentum"], "detectada", 60, ago(3), {
    evidence: ["Retorno 1h +2,2%"], entry: 24.61, invalidation: 23.7, target: 26.2,
  }),
  opp("OP-2003", "ARBUSDT", "Volume Anomaly", ["volume"], "shadow", 64, ago(800), {
    evidence: ["Dados atrasados na detecção"], entry: 0.55, invalidation: 0.52, env: "shadow", riskStatus: "rejeitado",
    riskLog: { at: ago(798), result: "rejeitado", checks: [{ name: "Qualidade dos dados", value: "atrasado 6 min", limit: "ok", ok: false }, { name: "Volume 24h elegível", value: "142 mi USDT", limit: "≥ 50 mi USDT", ok: true }], reason: "Dados atrasados. Encaminhado para shadow." },
  }),
];

// posições abertas: qty em unidade da moeda; custo em USDT
const POS_ALFA = [
  { id: "P-311", opp: "OP-1041", sym: "SOLUSDT", qty: 6.2, entry: 236.4, stop: 229.8, target: 249.5, openedAt: ago(140), fees: 1.47, env: "paper" },
  { id: "P-312", opp: "OP-1044", sym: "LINKUSDT", qty: 61, entry: 23.9, stop: 23.1, target: 25.6, openedAt: ago(96), fees: 1.46, env: "paper" },
];
const POS_LABS = [
  { id: "P-702", opp: "OP-2007", sym: "ETHUSDT", qty: 0.42, entry: 4401.0, stop: 4320.0, target: 4580.0, openedAt: ago(198), fees: 1.85, env: "paper" },
];

// trades encerrados (realizado)
const TRADES_ALFA = [
  { id: "T-288", opp: "OP-1018", sym: "BTCUSDT", qty: 0.0125, entry: 114800, exit: 117950, openedAt: ago(4290), closedAt: ago(2100), fees: 2.91, reason: "Alvo", env: "paper" },
  { id: "T-281", opp: "OP-1011", sym: "ETHUSDT", qty: 0.35, entry: 4310, exit: 4238, openedAt: ago(6890), closedAt: ago(6100), fees: 2.99, reason: "Stop", env: "paper" },
  { id: "T-274", opp: "OP-1002", sym: "AVAXUSDT", qty: 48, entry: 28.9, exit: 30.1, openedAt: ago(9800), closedAt: ago(8400), fees: 2.83, reason: "Alvo", env: "paper" },
];
const TRADES_LABS = [
  { id: "T-690", opp: "OP-2001", sym: "BTCUSDT", qty: 0.012, entry: 116200, exit: 115400, openedAt: ago(5000), closedAt: ago(4300), fees: 2.78, reason: "Invalidação", env: "paper" },
];

const ORDERS_ALFA = [
  { id: "O-9012", pos: "P-311", sym: "SOLUSDT", type: "Stop a mercado", purpose: "Stop", price: 229.8, qty: 6.2, status: "Pendente", at: ago(140) },
  { id: "O-9013", pos: "P-311", sym: "SOLUSDT", type: "Limite", purpose: "Alvo", price: 249.5, qty: 6.2, status: "Pendente", at: ago(140) },
  { id: "O-9014", pos: "P-312", sym: "LINKUSDT", type: "Stop a mercado", purpose: "Stop", price: 23.1, qty: 61, status: "Pendente", at: ago(96) },
  { id: "O-9015", pos: "P-312", sym: "LINKUSDT", type: "Limite", purpose: "Alvo", price: 25.6, qty: 61, status: "Pendente", at: ago(96) },
];
const ORDERS_LABS = [
  { id: "O-7101", pos: "P-702", sym: "ETHUSDT", type: "Stop a mercado", purpose: "Stop", price: 4320, qty: 0.42, status: "Pendente", at: ago(198) },
];

const EVENTS_ALFA = [
  { at: ago(2), kind: "sinal", text: "Volume Anomaly detectou pico em ARBUSDT (z=5,1) — dados atrasados 6 min", ref: "OP-1051" },
  { at: ago(12), kind: "sinal", text: "Breakout (simulado) sinalizou AVAXUSDT; Momentum não confirmou", ref: "OP-1050" },
  { at: ago(21), kind: "oportunidade", text: "OP-1049 ETHUSDT validada (score 74). Aguardando Risk Engine", ref: "OP-1049" },
  { at: ago(96), kind: "execucao", text: "Ordem de entrada LINKUSDT preenchida a 23,90 (slippage 0,04%)", ref: "P-312" },
  { at: ago(98), kind: "risco", text: "Risk Engine aprovou OP-1044: 6 verificações ok", ref: "OP-1044" },
  { at: ago(140), kind: "execucao", text: "Ordem de entrada SOLUSDT preenchida a 236,40 (slippage 0,06%)", ref: "P-311" },
  { at: ago(190), kind: "agente", text: "Order Flow pausado automaticamente: feed do livro Bybit sem dados", ref: "orderflow" },
  { at: ago(305), kind: "risco", text: "Risk Engine rejeitou OP-1038 INJUSDT: volume 24h < 50 mi. Encaminhado para shadow", ref: "OP-1038" },
  { at: ago(418), kind: "risco", text: "Risk Engine rejeitou OP-1036 PEPEUSDT: volume e spread", ref: "OP-1036" },
];
const EVENTS_LABS = [
  { at: ago(3), kind: "sinal", text: "Momentum detectou LINKUSDT", ref: "OP-2010" },
  { at: ago(9), kind: "oportunidade", text: "OP-2009 SOLUSDT em avaliação pelo Risk Engine", ref: "OP-2009" },
  { at: ago(198), kind: "execucao", text: "Entrada ETHUSDT preenchida a 4.401,00", ref: "P-702" },
];

const EXPERIMENTS_ALFA = [
  { id: "EXP-07", hypothesis: "Momentum 1h com filtro de volume z>3 supera momentum puro em altcoins líquidas", strategy: "Momentum v2.1", env: "backtest", period: "01/03/2026 – 31/08/2026", universe: "12 pares USDT (vol > 50 mi)", trades: 214, costs: "taxa 0,10% + slippage 5 bps", inSample: { ret: 8.4, dd: -6.1, hit: 44 }, outSample: { ret: 2.1, dd: -5.3, hit: 41 }, verdict: "inconclusivo", limits: "Fora da amostra com 61 operações — abaixo de 100. Não extrapolar.", status: "concluído" },
  { id: "EXP-08", hypothesis: "Breakout 20p com confirmação de fechamento reduz falsos rompimentos", strategy: "Breakout v1.3", env: "shadow", period: "18/08/2026 – hoje", universe: "5 pares", trades: 37, costs: "taxa 0,10% + slippage 5 bps", inSample: null, outSample: { ret: 1.2, dd: -2.8, hit: 46 }, verdict: "insuficiente", limits: "37 sinais em 28 dias — régua exige 100 resultados e 30 dias.", status: "em andamento" },
  { id: "EXP-05", hypothesis: "Filtro de funding extremo (Derivatives) evita entradas em topos locais", strategy: "Momentum v2.0 + funding", env: "backtest", period: "01/01/2026 – 28/02/2026", universe: "3 pares (BTC, ETH, SOL)", trades: 88, costs: "taxa 0,10% + slippage 5 bps", inSample: { ret: 3.9, dd: -4.4, hit: 47 }, outSample: { ret: -0.8, dd: -3.9, hit: 39 }, verdict: "reprovado", limits: "Degradação fora da amostra; possível overfitting do limiar de funding.", status: "concluído" },
];
const EXPERIMENTS_LABS = [
  { id: "EXP-L2", hypothesis: "Volume z>4 em pares de liquidez média antecipa continuação de 4h", strategy: "Volume v0.9", env: "backtest", period: "01/06/2026 – 31/08/2026", universe: "8 pares", trades: 132, costs: "taxa 0,10% + slippage 8 bps", inSample: { ret: 5.2, dd: -7.0, hit: 42 }, outSample: { ret: 1.9, dd: -6.2, hit: 40 }, verdict: "inconclusivo", limits: "Custos sensíveis: com slippage 12 bps o retorno fora da amostra fica negativo.", status: "concluído" },
];

const CRM_ALFA = {
  contacts: [
    { id: "C-1", name: "Mariana Costa", company: "Fundo Aurora", email: "mariana@aurora.fund", phone: "+55 11 98877-1201", tags: ["institucional", "quente"], owner: "Everton", updated: ago(60) },
    { id: "C-2", name: "Rafael Nunes", company: "RN Capital", email: "rafael@rncapital.com.br", phone: "+55 21 97711-3390", tags: ["family office"], owner: "Camila", updated: ago(300) },
    { id: "C-3", name: "Júlia Prado", company: "Prado Assessoria", email: "julia@pradoassessoria.com", phone: "+55 31 99234-8811", tags: ["parceiro"], owner: "Everton", updated: ago(1440) },
  ],
  deals: [
    { id: "D-1", title: "Aurora — plano Quant anual", contact: "C-1", value: 48000, stage: "proposta", owner: "Everton", close: "30/09/2026" },
    { id: "D-2", title: "RN Capital — piloto Pro", contact: "C-2", value: 9600, stage: "qualificacao", owner: "Camila", close: "15/10/2026" },
    { id: "D-3", title: "Prado — parceria de indicação", contact: "C-3", value: 12000, stage: "negociacao", owner: "Everton", close: "10/10/2026" },
    { id: "D-0", title: "Beta fechado — Vértice", contact: "C-1", value: 6000, stage: "ganho", owner: "Everton", close: "20/08/2026" },
  ],
  tasks: [
    { id: "K-1", title: "Enviar proposta revisada para Aurora", due: "16/09/2026", priority: "alta", owner: "Everton", link: "D-1", done: false },
    { id: "K-2", title: "Revisar EXP-08 antes de 100 sinais", due: "18/09/2026", priority: "média", owner: "Camila", link: "EXP-08", done: false },
    { id: "K-3", title: "Documentar rejeição OP-1036 no Lab", due: "15/09/2026", priority: "baixa", owner: "Everton", link: "OP-1036", done: true },
    { id: "K-4", title: "Ligar para RN Capital", due: "17/09/2026", priority: "média", owner: "Camila", link: "C-2", done: false },
  ],
  chats: [
    { id: "CH-1", contact: "C-1", queue: "Comercial", assigned: "Everton", status: "aberto", msgs: [
      { from: "them", text: "Conseguimos ver o relatório do Shadow Lab antes de fechar?", at: ago(50) },
      { from: "me", text: "Sim. Envio hoje o placar com veredito por versão e as limitações.", at: ago(48) },
      { from: "note", text: "Nota interna: não prometer rentabilidade — mostrar régua de 100 resultados.", at: ago(47) },
    ] },
    { id: "CH-2", contact: "C-2", queue: "Suporte", assigned: null, status: "fila", msgs: [
      { from: "them", text: "Como funciona o kill switch na carteira paper?", at: ago(20) },
    ] },
  ],
  tickets: [
    { id: "S-31", title: "Feed do livro Bybit sem dados (Order Flow)", category: "Integração", priority: "alta", owner: "Everton", status: "aberto", at: ago(185) },
    { id: "S-29", title: "Exportação Markdown do Lab sem tabela de custos", category: "Lab", priority: "média", owner: "Camila", status: "em andamento", at: ago(2000) },
  ],
  whatsapp: [
    { id: "W-1", name: "Comercial Mesa Alfa", type: "API oficial (Meta)", status: "conectado", owner: "Camila", number: "+55 11 4000-0101" },
    { id: "W-2", name: "Alertas operacionais", type: "Conector não oficial", status: "instável", owner: "Everton", number: "+55 11 98800-0202" },
  ],
};
const CRM_LABS = {
  contacts: [
    { id: "C-9", name: "Tiago Ferraz", company: "UFMG — Finanças Quant", email: "tiago@ufmg.br", phone: "+55 31 99100-7712", tags: ["pesquisa"], owner: "Ana", updated: ago(500) },
  ],
  deals: [{ id: "D-9", title: "Parceria acadêmica — dados", contact: "C-9", value: 0, stage: "qualificacao", owner: "Ana", close: "30/11/2026" }],
  tasks: [{ id: "K-9", title: "Preparar dataset do EXP-L2 para revisão", due: "20/09/2026", priority: "média", owner: "Ana", link: "EXP-L2", done: false }],
  chats: [],
  tickets: [],
  whatsapp: [],
};

export const ORGS = {
  alfa: {
    id: "alfa", name: "Mesa Alfa", plan: "Quant", desc: "Mesa proprietária pequena · 3 usuários",
    members: [
      { name: "Everton Silva", email: "everton@mesaalfa.com", role: "Proprietário" },
      { name: "Camila Rocha", email: "camila@mesaalfa.com", role: "Operador" },
      { name: "Diego Martins", email: "diego@mesaalfa.com", role: "Analista" },
    ],
    opps: OPPS_ALFA, positions: POS_ALFA, trades: TRADES_ALFA, orders: ORDERS_ALFA, events: EVENTS_ALFA, experiments: EXPERIMENTS_ALFA, crm: CRM_ALFA,
    watchlist: ["SOLUSDT", "LINKUSDT", "ETHUSDT", "AVAXUSDT"],
    killSwitch: "ATIVO", paused: false,
  },
  labs: {
    id: "labs", name: "Hunter Labs", plan: "Pro", desc: "Pesquisa quantitativa · 1 usuário",
    members: [{ name: "Ana Beatriz Lima", email: "ana@hunterlabs.dev", role: "Proprietário" }],
    opps: OPPS_LABS, positions: POS_LABS, trades: TRADES_LABS, orders: ORDERS_LABS, events: EVENTS_LABS, experiments: EXPERIMENTS_LABS, crm: CRM_LABS,
    watchlist: ["ETHUSDT", "SOLUSDT"],
    killSwitch: "ATIVO", paused: false,
  },
};

export const GAMIFICATION = {
  rules: [
    { rule: "Documentar uma decisão de risco no Lab", pts: 20, once: "por oportunidade" },
    { rule: "Concluir experimento com avaliação fora da amostra", pts: 50, once: "por experimento" },
    { rule: "Concluir tarefa dentro do prazo", pts: 10, once: "por tarefa" },
    { rule: "Semana sem violação de limite de risco", pts: 30, once: "por semana" },
    { rule: "Revisar oportunidade rejeitada e registrar aprendizado", pts: 15, once: "por oportunidade" },
  ],
  notRewarded: ["Quantidade de trades", "Volume negociado", "Exposição financeira", "Aumento de risco", "Volume de mensagens"],
  achievements: [
    { name: "Disciplina operacional", desc: "4 semanas seguidas sem violação de limite", progress: 3, total: 4 },
    { name: "Pesquisador", desc: "5 experimentos com avaliação fora da amostra", progress: 3, total: 5 },
    { name: "Documentador", desc: "20 decisões documentadas", progress: 14, total: 20 },
  ],
};

// ---------- cálculos compartilhados ----------
export const priceOf = (sym) => (MARKETS.find((m) => m.sym === sym) || {}).price || 0;
export const marketOf = (sym) => MARKETS.find((m) => m.sym === sym);

export function computePortfolio(org) {
  const initialUSDT = LIMITS.initialBRL / LIMITS.fxBRLUSDT;
  const realized = org.trades.reduce((s, t) => s + (t.exit - t.entry) * t.qty - t.fees, 0);
  const posRows = org.positions.map((p) => {
    const price = priceOf(p.sym);
    const cost = p.entry * p.qty;
    const value = price * p.qty;
    const unreal = value - cost - p.fees;
    const riskPlanned = (p.entry - p.stop) * p.qty; // perda até o stop (planejada, não garantida)
    return { ...p, price, cost, value, unreal, unrealPct: (unreal / cost) * 100, riskPlanned };
  });
  const allocated = posRows.reduce((s, p) => s + p.cost, 0);
  const feesOpen = posRows.reduce((s, p) => s + p.fees, 0);
  const cash = initialUSDT + realized - allocated - feesOpen;
  const marketValue = posRows.reduce((s, p) => s + p.value, 0);
  const equity = cash + marketValue;
  const unrealized = posRows.reduce((s, p) => s + p.unreal, 0);
  const totalPnl = realized + unrealized;
  const exposure = marketValue / equity;
  const riskAgg = posRows.reduce((s, p) => s + p.riskPlanned, 0) / equity;
  const byCoin = posRows.map((p) => ({ sym: p.sym, pct: p.value / equity }));
  // curva de patrimônio (demonstrativa): pontos a partir de trades encerrados + estado atual
  const curve = [initialUSDT];
  let acc = initialUSDT;
  [...org.trades].sort((a, b) => a.closedAt.localeCompare(b.closedAt)).forEach((t) => { acc += (t.exit - t.entry) * t.qty - t.fees; curve.push(acc); });
  curve.push(equity);
  const peak = Math.max(...curve);
  const maxDD = Math.min(...curve.map((v, i) => v / Math.max(...curve.slice(0, i + 1)) - 1));
  const feesTotal = org.trades.reduce((s, t) => s + t.fees, 0) + feesOpen;
  return { initialUSDT, realized, unrealized, totalPnl, cash, allocated, marketValue, equity, exposure, riskAgg, byCoin, posRows, curve, peak, drawdown: equity / peak - 1, maxDD, feesTotal, positionsCount: posRows.length };
}

export function riskEngine(org, o) {
  const pf = computePortfolio(org);
  const m = marketOf(o.sym);
  const riskUSDT = pf.equity * LIMITS.riskPerTrade;
  const perUnit = o.entry - o.invalidation;
  const qty = perUnit > 0 ? riskUSDT / perUnit : 0;
  const notional = qty * o.entry;
  const coinPct = ((pf.byCoin.find((c) => c.sym === o.sym) || {}).pct || 0) + notional / pf.equity;
  const checks = [
    { name: "Kill switch / pausa", value: org.killSwitch === "ATIVO" && !org.paused ? "liberado" : "bloqueado", limit: "liberado", ok: org.killSwitch === "ATIVO" && !org.paused },
    { name: "Volume 24h elegível", value: fmtVol(m.vol) + " USDT", limit: "≥ 50 mi USDT", ok: m.vol >= LIMITS.minVolume24hUSDT },
    { name: "Qualidade dos dados", value: m.quality, limit: "ok", ok: m.quality === "ok" },
    { name: "Liquidez (spread)", value: fmtNum(m.spread, 1) + " bps", limit: "≤ 8 bps", ok: m.spread <= 8 },
    { name: "Exposição total", value: fmtPct((pf.marketValue + notional) / pf.equity * 100), limit: "≤ 40%", ok: (pf.marketValue + notional) / pf.equity <= LIMITS.exposureMax },
    { name: "Exposição na moeda", value: fmtPct(coinPct * 100), limit: "≤ 10%", ok: coinPct <= LIMITS.exposurePerCoinMax },
    { name: "Risco agregado planejado", value: fmtPct((pf.riskAgg + LIMITS.riskPerTrade) * 100, 2), limit: "≤ 1,00%", ok: pf.riskAgg + LIMITS.riskPerTrade <= LIMITS.riskAggMax + 1e-9 },
    { name: "Posições simultâneas", value: String(pf.positionsCount + 1), limit: "≤ 5", ok: pf.positionsCount + 1 <= LIMITS.maxPositions },
    { name: "Invalidação definida", value: o.invalidation ? "sim" : "não", limit: "sim", ok: !!o.invalidation && perUnit > 0 },
  ];
  const failed = checks.filter((c) => !c.ok);
  return { checks, ok: failed.length === 0, failed, qty, notional, riskUSDT, reason: failed.length ? `Falhou em: ${failed.map((c) => c.name).join(", ")}.` : "Todas as verificações passaram." };
}

// ---------- formatação pt-BR ----------
export const fmtNum = (v, d = 2) => Number(v).toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
export const fmtUSDT = (v, d = 2) => fmtNum(v, d) + " USDT";
export const fmtBRL = (v) => "R$ " + fmtNum(v, 2);
export const fmtPct = (v, d = 1) => (v > 0 ? "+" : v < 0 ? "−" : "") + fmtNum(Math.abs(v), d) + "%";
export const fmtSigned = (v, d = 2) => (v > 0 ? "+" : v < 0 ? "−" : "") + fmtNum(Math.abs(v), d);
export const fmtPrice = (v) => (v >= 1000 ? fmtNum(v, 2) : v >= 1 ? fmtNum(v, v >= 100 ? 2 : 4) : v.toLocaleString("pt-BR", { maximumSignificantDigits: 4 }));
export const fmtVol = (v) => (v >= 1e9 ? fmtNum(v / 1e9, 2) + " bi" : v >= 1e6 ? fmtNum(v / 1e6, 1) + " mi" : fmtNum(v / 1e3, 0) + " mil");
export const fmtDT = (iso) => new Date(iso).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
export const fmtTime = (iso) => new Date(iso).toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
export function fmtAgo(iso, now = T0) {
  if (!iso) return "—";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `há ${s} s`;
  if (s < 3600) return `há ${Math.round(s / 60)} min`;
  if (s < 86400) return `há ${Math.round(s / 3600)} h`;
  return `há ${Math.round(s / 86400)} d`;
}
export const NOW_ISO = new Date(T0).toISOString();
export const nowIso = () => new Date().toISOString();
