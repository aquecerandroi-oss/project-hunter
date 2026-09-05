---
tags: [decisoes, adr, indice]
updated: 2026-09-05
---

# Architecture Decisions

Índice legível das ADRs em `docs/decisions/`. Cada ADR completa fica lá; aqui só o resumo e o porquê. Esta página também reúne as decisões de design mais importantes espalhadas por `docs/ARCHITECTURE.md` e `docs/DATABASE.md`, porque são as regras que qualquer implementação futura tem que respeitar.

## ADR 0001 — Adotar o fluxo do vibe-coding-toolkit

**Status:** aceito (2026-09-04). Define como o próprio desenvolvimento do Hunter é conduzido: sessão principal orquestra e commita, especialistas implementam; brainstorm → plano → ondas → revisão → commit; execução em ondas paralelas com dependências explícitas; quality gates (350 linhas por módulo, lint que nasce em `warn`); memória em duas camadas; hooks fail-open; escolha explícita de modelo por despacho. Alternativas descartadas: GitHub Spec Kit e BMAD (mais pesados), `aia-harness:init` (roster genérico). Consequência prática: nenhuma tarefa de milestone é despachada sem brief com arquivos e dependências, e `risk-engine-guardian`/`security-reviewer` são revisores obrigatórios em qualquer caminho que mova dinheiro ou toque auth.

## ADR 0002 — Camada de provedores LLM (Anthropic + OpenAI)

**Status:** aceito, implementação na Fase 2 (Intelligence Engine). Cria `hunter_core.llm` provedor-agnóstica (`LlmProvider` Protocol, `AnthropicProvider` e `OpenAIProvider`), seleção por `LLM_PROVIDER`/`LLM_MODEL`, com fallback e circuit breaker: LLM indisponível degrada para "sem análise", nunca para decisão automática. Motivada pelo lançamento do GPT-6 Astra (OpenAI) em 2026-09-03 e pelo desejo do produto de comparar provedores. Restrição inegociável: nenhuma IA entra no caminho Risk Engine → Execução. Alternativas descartadas: só Anthropic (lock-in), roteador externo tipo OpenRouter (terceiro na cadeia de segredos e dados de mercado).

## ADR 0003 — `obsidian/` como base de conhecimento viva do projeto

**Status:** aceito (2026-09-05). Cria esta pasta (`obsidian/`) como base de conhecimento do produto, separada do `vault/` pessoal do Sexta-feira (memória do agente, só por MCP) e de `docs/` (especificação normativa). `obsidian/` é Markdown puro, versionado, atualizado pelos agentes com ferramentas normais de arquivo sempre que uma implementação, bug, decisão ou mudança de estratégia for significativa; resume e linka para `docs/` em vez de duplicar. Entra na definition-of-done de cada milestone (seção OBSIDIAN UPDATED do relatório §77). Esta própria página é o "índice legível" que o ADR pede.

## Decisões de design que atravessam o produto (não são ADRs formais, mas são igualmente não-negociáveis)

- **Nenhum agente executa ordens.** Todo caminho de entrada é AGENT → PROPOSAL → RISK ENGINE → EXECUTION; saídas (stop, alvo, fechamento manual, kill switch) são sempre permitidas. Ver [[Risk Engine]].
- **Dinheiro é `Decimal`/`NUMERIC(28,10)`, nunca `float`; tempo é sempre UTC (`TIMESTAMPTZ`).** Vale para preço, quantidade, PnL e fee em todo o sistema — inclusive `funding_rate`, que usa `NUMERIC(28,10)` em vez do `NUMERIC(9,6)` de outros percentuais, porque um erro de arredondamento de 4% nesse número quebra as estratégias de derivativos.
- **Isolamento de tenant é duplo.** Repositórios `org_id`-scoped no código **e** Row Level Security forçada no Postgres em toda tabela de tenant, incluindo cada partição individualmente (o Postgres não herda política de uma tabela particionada pai). Ver `docs/DATABASE.md` §1.2 e §15.4.
- **Paper antes de live, sempre.** `ENABLE_LIVE_TRADING=false` é o valor padrão e atual em `.env.example`; `LiveExecutionAdapter` levanta `LiveTradingDisabled` até a Fase 4, com checklist de segurança, sandbox e ativação explícita por OWNER.
- **Toda decisão é explicável.** Score, sinal, proposta e trade persistem sua decomposição no momento em que foram tomados — nunca reconstruída depois.

## Relacionadas

[[System Overview]] · [[Risk Engine]] · [[Execution Engine]]

## Fontes

`docs/decisions/0001-adotar-vibe-coding-toolkit.md`, `docs/decisions/0002-camada-de-provedores-llm.md`, `docs/decisions/0003-base-de-conhecimento-obsidian.md`, `docs/ARCHITECTURE.md` §1, `docs/DATABASE.md` §1 e §15, `CLAUDE.md`

## Decisões de 2026-09-05 sobre ferramentas externas
- **ADR 0004 — CCXT:** segunda implementação do `ExchangeAdapter` na Fase 3 (endpoints privados e amplitude certificada); Binance e Bybit continuam próprias (a Astra mostrou que o parser WS do Bybit no ccxt.pro descarta `confirm`/timestamps). Pins exatos do pacote exigem projeto independente para avaliação.
- **2026-09-05 — Binance Skills Hub: não instalar.** Skills que dão a agentes de IA acesso autenticado à conta Binance (`binance-cli`) violam "nenhum agente executa ordens" e o isolamento de segredos; sinais externos opacos não entram no score. Detalhes na [[Architecture Decisions]] → ADR 0004 (seção relacionada).

## Decisão conjunta M1 — Claude ⇄ Astra (2026-09-05)
Desde 2026-09-05 as duas IAs trabalham unidas por regra do dono (`.claude/rules/astra-second-opinion.md`): a Astra (GPT-6 via Codex) opina em toda auditoria, plano e diff, executa tarefas mecânicas por brief (`infra/scripts/astra.sh run`) e discute decisões de projeto em rodadas num arquivo de transcrição (`infra/scripts/astra.sh dialogue`), até uma rodada abrir com **DECISÃO CONJUNTA**. A primeira decisão conjunta fechou o desenho do [[Market Collector]] do M1 em quatro rodadas (`.claude/state/dialogue-M1.md`):
- **Recovery de candles**: Postgres só recebe velas finais; REST `ON CONFLICT DO NOTHING`; bootstrap sem watermark pelas últimas 1500 velas com corte pela hora da exchange; detecção de buracos internos na janela de 24 h; velas + transição `open → recovered` na mesma transação; Redis com escritor único (WS), parcial nunca substitui final.
- **Liquidações**: identidade determinística `uuid5(exchange, symbol, side, price, qty, ts_ms)` como PK `(id, ts)` e como `event_id` da publicação (consumidores deduplicam); publicação best-effort após commit no M1 (limitação aceita; outbox no M2).
- **Supervisão**: toda tarefa do worker dentro de um `TaskGroup` via `forever()`; retorno normal é fatal; watchdog por conexão WS (30 s sem dado → reinício; 3 seguidos → fatal); `readiness_checks` no runtime com timeout.
- **Staleness por componente**: `ticker`, `book` e `mark` obrigatórios; `unavailable` / `degraded` / `stale` (> 10 s) / `ok`; idade calculada pelo `ts` da exchange do último evento aceito, nunca pelo flush; timestamps próprios por campo em `deriv`.
- **Rotas WS da Binance**: `/public/stream` para `@depth20` (sem sufixo) e `bookTicker`; `/market/stream` para `aggTrade`, `kline_1m`, `markPrice@1s`, `forceOrder`; contagem por streams (< 1024/conexão).
Plano: `docs/plans/M1.md`. Ver também [[Exchange Adapters]], [[WebSockets]], [[Monitoring]].

## Decisão conjunta SHADOW — contrato do Shadow Lab v0, antecipado aos milestones (2026-09-05)
Terceira decisão conjunta Claude ⇄ Astra (3 rodadas, [[Dialogos/SHADOW|transcrição]]; plano `docs/plans/SHADOW-LAB.md`, commit `fc336d9`). O dono pediu agentes "já fazendo compra e venda virtual" antes de qualquer dinheiro real. A resposta é o **Shadow Lab v0**: a PARTE 11 da diretiva (o Hunter registra *eu entraria aqui* e depois mede) rodando sobre o dado real do M1, **fora da ordem dos milestones** e **sem tocar a ordem deles**. É pesquisa, não produto de trading — não há carteira, ordens, fills, posições, PnL de portfolio nem Risk Engine; isso continua sendo M3/M4.

O que essa decisão fixa como regra permanente do produto, e não só do Lab:

- **Protocolo congelado na primeira ativação.** `strategy_id`, `version`, `code_ref`, `parameters_schema`, `default_parameters`, `params_hash`, timeframes, agregação, seed/âncora do ATR, política de reentrada, perfil de custos e modelo de outcome ficam imutáveis desde a primeira ativação, **em qualquer status** — deprecated e reativada inclusive — por *trigger* no banco, não por convenção. Conteúdo diferente = versão nova. A rota de fuga que a Astra encontrou (*deprecated → alterar parâmetros → reativar*, ou zerar `activated_at`) é fechada explicitamente. Migração `0002_shadow_lab` (tarefa S0) precede qualquer ativação.
- **Serialização canônica versionada (`params_format = 1`).** Chaves ordenadas, decimais como string normalizada sem zeros à direita nem expoente, timestamps ISO-8601 UTC com `Z`, ausentes explícitos como `null`, com vetores de teste provando identidade igual para representações equivalentes. Ordenar chaves sozinho não resolve identidades numericamente equivalentes.
- **Envelope imutável da decisão.** `agent_signals.supporting_features` é escrito uma vez, na decisão, e nunca depois: `observation_ts`, `decision_at`, disponibilidade/qualidade por entrada, valores calculados, fontes duráveis, elegibilidade do universo no instante, `purpose`, `cohort`. Metadados posteriores (excursões) vão para `signal_outcomes.meta`, campo separado.
- **Um número que a fonte não determina vira nulo com motivo, nunca um valor plausível.** Cenário que decidiu: entrada 100, stop 99, alvo 102, primeira barra low 98 / high 103 — sob `stop-first`, o OHLC não prova excursão favorável de 3 antes da saída, e zero também seria invenção. Logo `mfe = null`, `bounds.mfe = [0, 3]`, `ambiguous = true`. Mesma regra para `R_net` quando o funding aplicável não é apurável, e para PF sem perdas (nulo com motivo, nunca número arbitrário). **Vale para todo o produto**, não só para o Lab.
- **Métricas com nome certo.** *Taxa de alvo entre toques resolvidos* ≠ *taxa de lucro líquido* ≠ *expectancy líquida hipotética em R*. Exemplo que separa as duas últimas: +2 R e −1 R dão expectancy +0,5 R e taxa de lucro 50%. **PnL e drawdown de carteira: não aplicável** enquanto não houver carteira — soma de R de sinais sobrepostos não é equity e seu drawdown depende da ordenação.
- **Limiar editorial antes de qualquer conclusão.** Abaixo de **100 outcomes avaliáveis E 30 dias distintos**, só descrição e "inconclusivo". Acima, ainda assim "pesquisa", nunca promessa, com incerteza por reamostragem em blocos de tempo (mercados simultâneos são dependentes), sensibilidade a custos, variantes tentadas registradas e avaliação futura reservada.
- **Isolamento de pesquisa.** Stream próprio `shadow.signals.emitted`, `purpose = research_only` persistido no envelope e no evento, recusado por teste pelo futuro proposal builder; consenso do M2 com peso zero; `active` numa versão **não** implica elegibilidade de execução (o M4 terá `execution_eligible` explícito). Nada aqui pode ordenar coisa alguma.
- **Durabilidade antes de publicação.** Sinal + outcome inicial + episódio/checkpoint + linha de outbox na mesma transação, ACK só após o commit; `shadow_outbox` antecipa o contrato T2.9, que a absorve sem perder pendências nem identidades. `INSERT ... ON CONFLICT (id) DO NOTHING` com `id = uuid5(NAMESPACE_SHADOW, canonical(strategy_version_id, market_id, params_hash, source_bar_close, cohort))`, `decision_at` fora do hash.

**Consequência para os milestones:** S0 e S1 correm em paralelo com o fim do M1 (arquivos disjuntos); T2.1 do M2 passa a **referenciar** a migração `0002_shadow_lab` em vez de recriar seus objetos; T2.8 cede `EXP-0001`/`EXP-0002` ao Shadow e fica com `EXP-0003`. Ver [[Strategies]], [[Momentum Agent]], [[Volume Agent]], [[Experiments Index]], [[Market Collector]] (`tracking_hold`).
