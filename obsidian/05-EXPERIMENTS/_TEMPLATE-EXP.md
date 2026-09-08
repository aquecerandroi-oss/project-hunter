---
tags: [experimento, template]
updated: 2026-09-08
status: planejado
owner: sexta-feira
exp: EXP-NNNN
strategy: ""
version: ""
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-NNNN — <slug curto do experimento>

> Copie este arquivo para `EXP-NNNN-<slug>.md` (número sequencial, `NNNN` com 4 dígitos) quando o experimento **começar** — não quando terminar. A seção "Protocolo" é escrita uma vez e **nunca** muda; as avaliações são **acrescentadas** abaixo, datadas. Uma repetição do mesmo teste com qualquer mudança de conteúdo é um `EXP-NNNN` novo, linkado a este. Ver [[Experiments Index]] e [[Dialogos/SHADOW]].

## Hipótese (congelada)

<uma frase: o que se espera provar ou refutar>

## Portão de desenho (C1–C8) — congelado, escrito **antes** de existir código

> **Quem escreve:** o quant-engineer, no EXP, antes de abrir o primeiro arquivo da estratégia. **Quem confere:** o `code-reviewer`, que recusa uma entrega de estratégia cujo EXP não tenha esta seção preenchida com um veredito. Método trazido do `edge-strategy-reviewer` (claude-trading-skills, MIT) e adaptado a este projeto; onde ele conflita com a `docs/plans/SHADOW-LAB.md` ou a `docs/plans/REPLICATION.md`, **as nossas regras mandam**. Este portão é sobre o **desenho** — ele não mede desempenho, não substitui replay, estresse, prospectivo ou replicação, e um PASS aqui não é evidência de vantagem nenhuma.

| # | Critério | O que se pergunta aqui | Veredito | Justificativa (obrigatória) |
|---|---|---|---|---|
| C1 | Plausibilidade da vantagem | Qual é o **mecanismo causal** — quem está do outro lado da operação e por que ele aceita perder? Uma tese sem mecanismo ("o momentum funciona") é genérica por definição. Link para a KB que sustenta | | |
| C2 | Risco de sobreajuste | Quantas condições de entrada (incluindo filtros de regime e de tendência) e quantos limiares? Cada limiar com mais de **2 algarismos significativos** precisa de origem declarada | | |
| C3 | Adequação da amostra | Quantas oportunidades por ano **por mercado** no universo de referência? Estimativa declarada antes de rodar, com a conta | | |
| C4 | Dependência de regime | A tese vale em `BTC_BULL`, `BTC_BEAR`, `SIDEWAYS`, alta e baixa volatilidade? Se vale em um só, o plano de validação **precisa** dizer como isso será medido (`market_regimes` no envelope) | | |
| C5 | Calibração das saídas | Stop e alvo em ATR, com o R/R resultante; a distância do stop cabe entre `min_stop_distance_pct` (0,3 %) e `max_stop_distance_pct` (3 %) do `paper_v1`? Horizonte declarado | | |
| C6 | Concentração de risco (**limites do `paper_v1`**) | A estratégia cabe no preset sem pedir exceção: `risk_per_trade_pct` 0,25 %, risco planejado agregado 1 %, exposição por ativo 10 %, exposição total 40 %, `max_concurrent_positions` 5, `max_beta_btc_exposure` 0,5, `max_leverage` 1 (SPOT, sem short). Uma estratégia que só faz sentido com mais posições simultâneas ou mais risco por operação **não é candidata** — é um pedido de mudança de perfil, que é outra conversa e é do Everton | | |
| C7 | Realismo de execução | Os mercados são **executáveis no SPOT** (`max_leverage = 1`), passam o piso de **50 M USDT** de volume 24 h (`min_liquidity_usd_24h`, `docs/PIPELINE.md` §1d) e a entrada cabe no atraso máximo declarado (`max_entry_delay_s`, 120 s: `entry_bar_open − source_bar_close`)? Custos assumidos citados (2 bps de spread total, 5 bps de slippage por lado, 4 bps de taxa por lado) | | |
| C8 | Qualidade da invalidação | Qual é a regra de invalidação **desta** estratégia? Herdar a do `momentum_v1` (fechamento de 15 min abaixo da máxima anterior) só é aceitável **com argumento explícito** de por que ela é a regra certa aqui — copiar a invalidação alheia é a forma mais silenciosa de não ter uma | | |

**Regras mecânicas (não são opinião):**

- **REJECT** se a entrada tem **mais de 8 condições** (contando filtros de regime e de tendência) — mais estreito que o limite de 10/12 da fonte, porque o nosso universo é menor e a nossa janela é de semanas, não de anos.
- **REJECT** se **qualquer limiar** tem mais de **2 algarismos significativos** sem motivo declarado (`atr_pct_min = 0,0089` precisa dizer de onde veio; `1,5` e `0,003` não precisam). Limiar garimpado é o sintoma mais barato de sobreajuste ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]], [[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]]).
- **REVISE** se a frequência esperada for **< 30 oportunidades por ano por mercado** no universo de referência: abaixo disso a régua de maturidade (100 desfechos avaliáveis **E** 30 dias distintos) não fecha em prazo humano e o experimento nasce inconclusivo.
- **REVISE** se o experimento não nomear o seu **controle predeclarado** (`docs/plans/REPLICATION.md` §3.6): uma hipótese sem contraste não é testável, e num mês de alta qualquer regra comprada com stop e alvo em ATR parece boa.
- Um **REJECT** em C1 ou C2 é REJECT do experimento, sem média com os outros critérios.

**Veredito do portão:** `PASS` | `REVISE` | `REJECT` — <data, quem assinou, e o que muda se for REVISE>

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key` + `strategy_versions.version`
- **code_ref:** módulo + hash do código da estratégia e das calculadoras
- **params_hash / params_format:** `<hash>` / `1`
- **Parameters:** JSON completo de `default_parameters` (nada implícito)
- **Timeframe de decisão / de outcome:** <ex.: 15 min / 1 min, UTC>
- **Agregação e ATR:** <ex.: 1 m → 15 m só com barras UTC contíguas e finais; ATR = Wilder(14) de 15 min, seed/âncora persistidos>
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com `entry_bar_open − source_bar_close ≤ 120 s`
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra → **stop** (convenção pessimista); horizonte <4 h | 2 h> contado da entrada
- **Custos assumidos (hipóteses, não tarifas verificadas):** spread total <2> bps, slippage <5> bps por lado, taxa <4> bps por lado; funding assinado
- **Política de reentrada:** um acompanhamento `pending_entry|active` por `(strategy_version_id, market_id, cohort)`; rearme só após barra elegível com a condição falsa **depois** do término anterior
- **Cohort:** `prospective` | `replay:<run_id>`
- **Controle predeclarado:** <o padrão do `REPLICATION.md` §3.6 — mesmos mercados e horários, mesma geometria, entradas de tempo aleatório semeadas na mesma frequência, sem o filtro de entrada — ou outro, nomeado aqui e congelado; a vantagem é reportada como Δ contra ele>
- **Universo elegível:** <critério e onde a composição do instante fica gravada>
- **Markets:** <exchanges e filtros>
- **Data de início da coleta:** <AAAA-MM-DD>

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de <AAAA-MM-DD> — `as_of = <timestamp UTC>`

**SQL usado:**

```sql
-- cole aqui a consulta exata, com os parâmetros
```

**Cobertura (contagens completas):**

| Emitidos | Pendentes | Entradas | Não entradas (por motivo) | Ativos | Target | Stop | Expired | Invalidated | Censurados | Funding indisponível |
|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |

**Métricas (distintas, com denominador explícito):**

| Métrica | Valor | Denominador | Observação |
|---|---|---|---|
| Taxa de alvo entre toques resolvidos | | `target + stop` | não é taxa de lucro |
| Taxa de lucro líquido | | encerrados avaliáveis | `R_net > 0` / encerrados avaliáveis |
| Expectancy líquida hipotética em R por entrada encerrada avaliável | | mesma população | média de `R_net` |
| Profit Factor | | Σ positivos / \|Σ negativos\| | **nulo com motivo** se não houver perdas |
| MFE/MAE | | barras completas | nulo quando o OHLC não determina o extremo; limites em `meta.excursions` |
| Soma de R hipotéticos | | ordenação declarada | não é equity |
| **PnL de carteira** | **não aplicável** | — | não há carteira no Shadow Lab |
| **Max Drawdown de carteira** | **não aplicável** | — | idem |

- **Dias distintos com outcome avaliável:** <n>
- **Versão da métrica / proveniência:** <ex.: `shadow_metrics_v1`, tabelas `agent_signals` + `signal_outcomes`>
- **Result:** confirmou | refutou | **inconclusivo** — obrigatoriamente `inconclusivo` abaixo de **100 outcomes avaliáveis E 30 dias distintos**
- **Conclusion:** <texto; sem promessa, é pesquisa>
- **Next Action:** <o que se faz a seguir — nunca "ativar automaticamente a variante vencedora">

### Avaliação de <próxima data>

<acrescente uma seção nova; não edite a anterior>

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
|  |  |  |  |

## Relacionadas

[[Experiments Index]] · [[Strategies]] · [[Strategy Performance]] · [[Dialogos/SHADOW]]

## Fontes

<caminhos, migrações e queries usadas para extrair os números acima>
