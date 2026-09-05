---
tags: [experimento, template]
updated: 2026-09-05
status: planejado
---

# EXP-NNNN — <slug curto do experimento>

> Copie este arquivo para `EXP-NNNN-<slug>.md` (número sequencial, `NNNN` com 4 dígitos) quando o experimento **começar** — não quando terminar. A seção "Protocolo" é escrita uma vez e **nunca** muda; as avaliações são **acrescentadas** abaixo, datadas. Uma repetição do mesmo teste com qualquer mudança de conteúdo é um `EXP-NNNN` novo, linkado a este. Ver [[Experiments Index]] e [[Dialogos/SHADOW]].

## Hipótese (congelada)

<uma frase: o que se espera provar ou refutar>

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
