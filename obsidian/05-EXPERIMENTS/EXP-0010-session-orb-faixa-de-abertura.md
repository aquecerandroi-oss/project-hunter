---
tags: [experimento, session-orb, calendario, shadow-lab]
updated: 2026-09-08
status: em-andamento
owner: sexta-feira
exp: EXP-0010
strategy: session_orb
version: v1
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-0010 — rompimento da faixa de abertura de sessão (`session_orb_v1`)

> **Arquivado pela Sexta-feira em 2026-09-08 (T3.32b)** a partir do rascunho do `quant-engineer`
> (T3.33, `.claude/state/exp-drafts/EXP-0010-session-orb-faixa-de-abertura.md`).
> **Nada foi rodado. Nada foi ativado.** "Hipótese" e "Protocolo" **congelados**; avaliações
> **acrescentadas** abaixo, datadas. Brief: `.claude/state/brief-T3.33c-session_orb_v1.md`.
> Esta é a única das quatro cuja **família é nova** no catálogo (`session_orb` em
> `infra/scripts/seed_reference.py`).
>
> **Acréscimo de 2026-09-08 (tarde, T3.33h), sem apagar nada acima:** o módulo foi escrito e
> commitado (T3.33c, `3ed17bb`), o portão C1–C8 foi preenchido abaixo (**REVISE**, 62,5) e o teto de
> pedágio (**0,3333 R**) está confirmado. **Nenhuma ativação, nenhuma coorte, nenhuma avaliação** —
> ativação e replay estão em voo na T3.33f, e `result` continua `nao-iniciado` por isso.

## Hipótese (congelada)

Num perpétuo USDT, a faixa (máxima e mínima) da **primeira hora** de uma das três sessões
declaradas — Ásia 00:00 UTC (21:00 de Brasília do dia anterior), Europa 07:00 UTC (04:00 de
Brasília), EUA 13:00 UTC (10:00 de Brasília) — carrega informação: um fechamento de 15 min acima da
máxima dessa faixa, nas quatro horas seguintes, com volume relativo ≥ 1,3, tem expectancy líquida
hipotética maior que zero, com stop na **mínima da faixa** e alvo em **2 R nominais**.

**A ressalva antes da tese: cripto não tem sessão.** O mercado é 24/7 e "Ásia/Europa/EUA" é uma
convenção **nossa**, declarada em três parâmetros congelados. Esta versão existe justamente para que
a convenção possa ser refutada.

**E ela não é pescaria.** [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] e
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] já mostraram que **o relógio está
dentro dos nossos limiares sem que ninguém tenha decidido isso** (o piso de ATR% funciona, na
prática, como filtro de horário/regime). Aqui o relógio entra na **regra**, visível, com nome, e
refutável — em vez de continuar como efeito colateral.

Evidência externa: Crabel (ORB) e Zarattini & Aziz (2023, momentum intradiário no S&P 500). Índices
de ações, com abertura e fechamento de pregão reais. **Nada disso foi mostrado em cripto**, e a
transposição está declarada como do `quant-engineer`.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = session_orb` (**família nova**, acrescentada a
  `infra/scripts/seed_reference.py`), versão `v1`, `purpose = research_only`.
  Módulo `packages/core/hunter_core/strategies/session_orb_v1.py`.
- **`code_ref`:** digest por versão; os digests de `momentum_v1` (`…ab2e0398…`) e
  `volume_anomaly_v1` (`…9b8c14ab…`) **não se movem** com esta entrega (teste).
- **Pureza:** a sessão é resolvida **a partir de `ctx.source_bar_close`**, que já está no contexto.
  `evaluate` continua sem ler relógio nenhum, e há teste que adianta o relógio do sistema em um dia
  e exige a mesma decisão.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Regra de entrada (exata), na ordem:** elegibilidade → resolver `(sessão, abertura)` e
  `bars_since_open` (≤ 4 → `inside_opening_range`; > 20 → `outside_session_window`) → janela →
  janela de ATR (Wilder 14 × 15 m, 97 barras, `rolling_window_v1`) → faixa de abertura das **4
  primeiras barras** da sessão → `close(t) > range_high` → volume relativo ≥ 1,3 (mediana de 96
  barras, atual excluída) → `0,006 ≤ ATR% ≤ 0,05` → guarda de tamanho:
  `1,0 ≤ (close − range_low)/ATR ≤ 2,5`, senão `REJECTED / range_geometry`.
- **Geometria:** `stop = range_low` (um dado, como a mínima da barra do pico em
  `volume_anomaly_v1`); `risk = C − range_low`; `alvo1 = C + 2·risk`; alvo informativo `C + 4·risk`.
- **Invalidação (exata): NENHUMA.** A mínima da faixa **é** o nível estrutural, e já é o stop. Uma
  regra `close_below` separada ficaria ou acima do stop (um segundo stop que ninguém declarou) ou
  abaixo dele (código morto).
- **Horizonte:** 4 h (14 400 s). **Custo declarado:** pode transbordar para a sessão seguinte; isso é
  **medido**, não suposto — a primeira avaliação reporta a fração de desfechos cuja saída cai numa
  sessão posterior.
- **Custos assumidos:** spread total 2 bps, slippage 5 bps/lado, taxa 4 bps/lado,
  `max_entry_delay_s = 120`. Entrada/saída pelo perfil congelado do `docs/plans/SHADOW-LAB.md` §3.
- **Parâmetros congelados:** a tabela de `.claude/state/brief-T3.33c-session_orb_v1.md` §7, 21 chaves,
  incluindo as três horas de abertura em UTC.
- **Universo:** replay de abertura em ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT; `prospective` no universo
  elegível inteiro.

### Geometria — por que o alvo é em R e não em ATR

Com o stop dado pelo **dado** (a mínima da faixa), um alvo fixo em ATR faz a relação
ganho/risco nominal variar de 4:1 a 1,3:1 dentro da faixa permitida — duas estratégias com um nome
só. Com alvo em **2 R constantes**:

| risco da faixa (ATR) | ATR% | alvo | R_net no alvo | R_net no stop | equilíbrio |
|---:|---:|---|---:|---:|---:|
| 0,5 | 0,006 | fixo 2 ATR | 2,7744 | −1,3881 | 0,3335 |
| 2,0 | 0,006 | fixo 2 ATR | 0,7927 | −1,1102 | 0,5834 |
| 0,4 | 0,004 | **2 R** | 0,5440 | −1,6356 | 0,7504 |
| 1,0 | 0,006 | **2 R** | 1,5133 | −1,2112 | **0,4446** |
| 1,5 | 0,010 | **2 R** | 1,7929 | −1,0888 | 0,3778 |

O alvo constante em R mantém o equilíbrio entre 38 % e 45 % em toda a faixa permitida, e a mesma
tabela é o que fixa `range_risk_atr_min = 1,0`: abaixo disso os 20 bps de custo assumido comem a
operação antes de o mercado ter opinião (75 % de equilíbrio com faixa de 0,4 ATR).

### Premissas numéricas declaradas

As três horas de abertura são a divisão convencional de mesa cripto e **não são medidas**;
`range_bars = 4` (uma hora) é a forma de Crabel, não um ajuste; `session_window_bars = 20` limita a
sessão a cinco horas para que as três não se sobreponham na regra; `rvol_min = 1,3` é
deliberadamente mais frouxo que o 1,5 do `momentum_v1` porque a abertura de sessão já carrega uma
sazonalidade de volume.

## Portão C1–C8 — veredito de 2026-09-08, escrito **antes** do módulo (T3.33c)

**Quem escreveu:** **autoavaliação do `quant-engineer`** contra
`.claude/skills/edge-strategy-reviewer/references/review_criteria.md`. **Não é revisão viva da
Astra.** Não altera Hipótese nem Protocolo. Condições contadas como "entrada": posição na sessão,
janela da sessão, `close > range_high`, `rvol ≥ 1,3`, `ATR% ≥ 0,006`, `ATR% ≤ 0,05`,
`range_risk ≥ 1,0`, `range_risk ≤ 2,5` = **8**; `trend_filter` = 0.

| # | critério | peso | sev. | nota | por quê |
|---|---|---:|---|---:|---|
| C1 | plausibilidade do edge | 20 | pass | 80 | mecanismo causal declarado (participação chega em blocos horários; a primeira hora fixa a faixa) e refutável |
| C2 | risco de sobreajuste | 20 | pass (contagem) | **30** | 8 condições ≤ 10 → 80, **−50**: cinco limiares com casa decimal (1,3 · 0,006 · 0,05 · 1,0 · 2,5) |
| C3 | amostra | 15 | pass | 80 | `252 × 0,8⁸ = 42,3` oportunidades/ano pela fórmula do portão (ver ressalva) |
| C4 | dependência de regime | 10 | **warn** | 40 | o plano de validação estratifica por **sessão**, não por regime do BTC |
| C5 | calibração da saída | 10 | pass | 80 | alvo = 2 R ≥ 1,5; stop máximo possível = `atr_pct_max × range_risk_atr_max` = **12,5 %** < 15 % (tem teste) |
| C6 | concentração de risco | 10 | pass | 80 | não há sizing: `research_only`, um acompanhamento por (versão, mercado, coorte) |
| C7 | realismo de execução | 10 | pass | 80 | há filtro de volume (`rvol ≥ 1,3`); `export_ready_v1` não se aplica |
| C8 | qualidade da invalidação | 5 | **fail** | 10 | `invalidations = ()` |

**Escore ponderado = 62,5 → veredito `REVISE`** (C1/C2 não falham, então não há REJECT imediato; há um
`fail`, então não há PASS).

**Divergências declaradas em vez de consertadas:**

1. **C8 é a hipótese, não esquecimento.** A mínima da faixa *é* o nível estrutural e já é o **stop**;
   uma `close_below` separada ficaria acima do stop (um segundo stop que ninguém declarou) ou abaixo
   dele (código morto). É a mesma forma da `volume_anomaly_v1`, e está amarrada a
   [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]]: **não** se afirma que remover invalidação
   melhora nada.
2. **C2 pune declarar número.** Os cinco "limiares decimais" são exatamente os parâmetros congelados
   que tornam a versão auditável; escondê-los em constantes redondas seria pior. Fica registrado que
   o portão não distingue "limiar ajustado" de "limiar declarado".
3. **C3 mede em dias de pregão.** A fórmula supõe uma barra por dia; aqui são 96 barras de 15 min por
   dia por mercado. A frequência de planejamento honesta é 0,3–1 entrada/mercado/dia, e o teste de
   verdade é K1/K2, não este 42,3.
4. **C4 fica em `warn` de propósito.** Há decomposição obrigatória **por sessão** e a regra dos 70 %,
   mas **não** há estratificação por regime do BTC. Não foi inventada uma para tirar nota — e o
   replay das irmãs mostrou que ela seria **impossível** hoje: `market_regimes` tem uma linha no
   banco inteiro.

**A divergência de método que continua aberta, e é da Astra:** ela recomendou deixar abertura de
sessão **fora** desta rodada, porque a hipótese é por construção uma afirmação sobre calendário
([[Dialogos/2026-09-08-quatro-estrategias]]). A decisão foi seguir assim mesmo, com a regra dos 70 %
como cláusula de morte. **Divergência assumida, registrada, não vencida por argumento.**

**A ressalva da revisão da T3.33c que sobrevive ao commit:** o **horizonte de 4 h transborda de
sessão** — é custo declarado, não suposto, e a primeira avaliação **tem** de publicar a fração de
desfechos cuja saída cai numa sessão posterior.

## O teto de pedágio desta geometria (confirmação pedida contra a T3.32)

A T3.32 mostrou que `custo_R × risco%` = **0,0020 constante** nas dez populações medidas —
aritmética (20 bps de ida e volta divididos pela distância percentual ao stop), não estatística.
Aplicado aos pisos congelados desta versão (`Decimal`, prec 28, travado em teste):

```
ida e volta            = 2 + 2×5 + 2×4 bps                = 0,002 do preço
risco% no pior caso    = range_risk_atr_min × atr_pct_min = 1,0 × 0,006 = 0,006
pedágio máximo         = 0,002 / 0,006                    = 0,3333 R
risco% no melhor caso  = 2,5 × 0,05                       = 0,125
pedágio mínimo         = 0,002 / 0,125                    = 0,0160 R
```

**O teto de custo desta geometria é 1/3 de R**, contra os **0,6152 R** medidos na coorte de replay da
`volume_anomaly v2` e os **0,1506 R** da `momentum v1` prospectiva. É o piso
(`range_risk_atr_min = 1,0` com `atr_pct_min = 0,006`) que impede a versão de repetir a doença da
`volume_anomaly`: lá o risco inicial mediano era 0,41 % do preço e o pedágio comia mais de meio R
antes de o mercado abrir a boca.

A tabela de geometria do brief §6 fecha nos quatro dígitos:

| risco da faixa | ATR% | R_net no alvo | R_net no stop | equilíbrio |
|---:|---:|---:|---:|---:|
| 1,0 ATR (piso) | 0,006 | 1,5133 | −1,2112 | **0,4446** |
| 1,5 ATR | 0,010 | 1,7929 | −1,0888 | 0,3778 |
| 2,5 ATR (teto) | 0,050 | 1,9725 | −1,0102 | 0,3387 |

O alvo em R constante mantém o equilíbrio entre **33,9 % e 44,5 %** em toda a faixa permitida — que é
a razão de o alvo não ser em ATR.

## O que falsifica esta hipótese

- **K1/K2/K3/K4/K5** de `.claude/state/notes-T3.33.md` §5.1.
- **Específico e obrigatório:** se **uma única sessão** carregar mais de 70 % das decisões, a
  hipótese não é "sessões", é "uma hora específica", e tem de ser **reenunciada como tal antes** de
  qualquer avaliação seguinte — reenunciar depois de ver o resultado é seleção retrospectiva
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **Decomposição por sessão obrigatória** na primeira avaliação: n, avaliáveis, expectancy e
  cobertura por sessão, lado a lado.
- **Se a expectancy por sessão for indistinguível entre as três**, o rótulo de sessão não está
  fazendo trabalho nenhum e o que sobra é um rompimento de faixa de 1 h qualquer — o que é uma
  hipótese diferente e mais fraca.

## O que este experimento **não** prova

- **Não decide "qual sessão é a boa".** Escolher a melhor das três depois de ver as três é
  exatamente o data snooping de [[KB-0003-rompimento-de-canal-e-data-snooping]]; qualquer versão por
  sessão única é uma versão **nova**, com janela futura reservada.
- **Multiplicidade:** uma de quatro versões abertas no mesmo dia; T-037 do
  [[Registro de Tentativas]].
- **O replay de abertura não confirma nada**; sai rotulado **REPLAY**.
- **Mistura de slot** com as outras versões.
- **PnL de carteira / Max Drawdown de carteira:** **não aplicável** — `research_only`, sem carteira.

## Avaliações (acrescentadas, nunca reescritas)

**Nenhuma ainda — e o estado em 2026-09-08 é "pendente", não "não existe".** O módulo
`session_orb_v1` foi escrito e **commitado** em `3ed17bb` (T3.33c: 45 testes próprios, prova de
mutação, digests das versões vivas idênticos), com `params_hash`
`cdb9516b293276095f4a8c2210d60ade0a4448cac46cce827f58bc3f8908d5e0`. **A ativação e o replay de dia
um estão em voo na T3.33f** (`.claude/state/brief-T3.33f-breakout-v2-explain-ledger-session-orb.md`)
— e a família é **nova** no catálogo, então `infra/scripts/seed.py` roda **antes** de
`activate_strategy_version.py`, ou a ativação não acha a linha.

Nada é preenchido aqui antes de existir. A primeira avaliação será acrescentada, datada, com: coorte,
janela, mercados, recibos do livro-razão, comandos exatos, cobertura completa, métricas com
denominador explícito, **decomposição por sessão** (a regra dos 70 %), **fração de desfechos cuja
saída cai numa sessão posterior**, distribuição de `range_risk_atr`, `Result` e `Next Action`.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| alvo fixo de 2 ATR | 2026-09-08 | recusado **antes** de rodar: com stop no dado, o ganho/risco varia de 4:1 a 1,3:1 | esta página, seção Geometria |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] · [[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[Registro de Tentativas]] ·
[[Dialogos/2026-09-08-quatro-estrategias]]

## Fontes

`.claude/state/notes-T3.33.md` · `.claude/state/brief-T3.33c-session_orb_v1.md` ·
`infra/scripts/seed_reference.py` · `infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py`
