---
tags: [experimento, session-orb, calendario, shadow-lab]
updated: 2026-09-08
status: em curso
owner: sexta-feira
exp: EXP-0010
strategy: session_orb
version: v1
result: inconclusivo
evaluable: 20
days: 9
last_eval: 2026-09-08 (replay de 31 d, coorte `replay:3fb9dda2…`, T3.33g — inconclusivo)
---

# EXP-0010 — rompimento da faixa de abertura de sessão (`session_orb_v1`)

> **RASCUNHO do quant-engineer (T3.33, 2026-09-08).** Para a Sexta-feira arquivar em
> `obsidian/05-EXPERIMENTS/EXP-0010-session-orb-faixa-de-abertura.md` e ligar a partir de
> [[Strategy Backlog]], [[KB-0009-o-efeito-do-quarto-de-hora]],
> [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]],
> [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] e [[Experiments Index]].
> Não editei `obsidian/**`.
>
> **Nada foi rodado. Nada foi ativado.** "Hipótese" e "Protocolo" **congelados**; avaliações
> **acrescentadas** abaixo, datadas. Brief: `.claude/state/brief-T3.33c-session_orb_v1.md`.

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
transposição está declarada como minha.

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
  `max_entry_delay_s = 120`. Entrada/saída pelo perfil congelado do SHADOW-LAB §3.
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
- **Multiplicidade:** uma de quatro versões abertas no mesmo dia.
- **O replay de abertura não confirma nada**; sai rotulado **REPLAY**.
- **Mistura de slot** com as outras versões.

## Avaliações (acrescentadas, nunca reescritas)

### 2026-09-08 — Avaliação (replay, dia um) — T3.33g

**REPLAY, não coleta prospectiva.** A janela avaliada (2026-08-08 → 2026-09-08) é a **mesma** que
gerou a hipótese. Nada aqui confirma coisa alguma; serve para **matar**, não para promover.

**Ativação:** `session_orb v1`, `purpose research_only`, em **2026-09-08T19:42:56,116683Z**
(16:42:56 de Brasília), `code_ref hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5…`
— o digest que o protocolo exigia, conferido no `--dry-run` antes de escrever.
**Coorte:** `replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19`, duas fatias contíguas, 4 mercados,
**11 904 barras**, 0 erros.

**População:** 39 barras dispararam; **20** viraram decisão (as 19 restantes caíram na barreira de
re-arme — um acompanhamento por versão/mercado/coorte). 20 terminais, **cobertura de `R_net` 100 %**,
**9 dias distintos**, 4 mercados.

| métrica | valor |
|---|---:|
| decisões | **20** (0,161 por mercado-dia; 124 mercado-dias) |
| avaliáveis | 20 (100 %) |
| expectancy **bruta** (sem custo nenhum) | **−0,0501 R** |
| expectancy **ex-funding** | **−0,1930 R** |
| expectancy **líquida** (`R_net`) | **−0,1928 R** |
| pedágio medido (`custo_R`) | **0,1428 R** (mínimo 0,0825 · máximo 0,2221) |
| soma de `R_net` | **−3,86 R** |
| taxa de acerto (`target`) | **10,0 %** (2 de 20) |
| profit factor líquido | **0,662** |

**Decomposição por sessão (obrigatória, e o teste dos 70 %):**

| sessão | n | % das decisões | exp. bruta | exp. líquida | soma `R_net` | PF | acerto | dias |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| asia (00:00Z) | 6 | 30,0 % | +0,0086 | **−0,1454** | −0,87 | 0,666 | 0,0 % | 4 |
| europe (07:00Z) | 7 | 35,0 % | −0,1834 | **−0,3257** | −2,28 | 0,484 | 0,0 % | 4 |
| us (13:00Z) | 7 | 35,0 % | +0,0328 | **−0,1005** | −0,70 | 0,839 | 28,6 % | 5 |

**A regra dos 70 % não dispara** (máximo 35 %). A hipótese **não** precisa ser reenunciada como "uma
hora específica" — e este é o resultado mais informativo do dia: a amostra é notavelmente equilibrada
entre as três sessões. O que **não** sobrevive é o outro lado da mesma regra: as três expectancies
são negativas e, com n = 6/7/7, **indistinguíveis entre si**. Pelo critério já congelado nesta
página ("se a expectancy por sessão for indistinguível entre as três, o rótulo de sessão não está
fazendo trabalho nenhum"), o rótulo de sessão **não fez trabalho nenhum** nesta janela. O que resta é
um rompimento de faixa de uma hora qualquer — hipótese diferente e mais fraca.

**Transbordo de sessão (o custo declarado, medido e não suposto):**

| leitura | n | fração |
|---|---:|---:|
| saída **depois do fim da janela de 5 h** da sessão de entrada | 11 / 20 | **55,0 %** |
| saída numa **sessão declarada posterior** (outra abertura) | 4 / 20 | **20,0 %** |

As quatro que caem em outra sessão: SOL 08-21 03:15 asia→europe (horizonte), DOGE e XRP 08-27 10:30
europe→us (horizonte), ETH 08-27 10:30 europe→us (stop).

**Livro de motivos (`--explain-ledger`, 11 904 linhas, uma por barra avaliada):**

| motivo | n | % das barras | asia | europe | us |
|---|---:|---:|---:|---:|---:|
| `outside_session_window` | 4 092 | 34,375 | 868 | 372 | 2 852 |
| `no_range_break` | 4 003 | 33,627 | 1 305 | 1 431 | 1 267 |
| `inside_opening_range` | 1 860 | 15,625 | 620 | 620 | 620 |
| `rvol_low` | 820 | 6,888 | 352 | 255 | 213 |
| `atr_out_of_range` | 575 | 4,830 | 164 | 152 | 259 |
| `range_geometry` | 279 | 2,344 | 44 | 67 | 168 |
| `warmup` (`unavailable`) | 236 | 1,983 | 108 | 64 | 64 |
| `signal` | 39 | 0,328 | 11 | 15 | 13 |
| `no_session_open` | **0** | 0,000 | — | — | — |

`no_session_open` **nunca ocorreu**, como a CONCERN 3 da `notes-T3.33c` previu: com as aberturas
congeladas, a asia às 00:00 cobre o dia inteiro e o ramo é inalcançável. Fica testado, não afirmado.

**A guarda de tamanho é o funil real desta versão.** Das 279 recusas por `range_geometry`,
**277 são por faixa larga demais** (`range_risk_atr > 2,5`) e apenas **2** por faixa estreita demais:

```
range_risk_atr nas recusas: n=279  min 0,921  p25 3,468  mediana 4,438  p75 5,955  max 9,445
```

Ou seja: na maioria das vezes em que o preço rompe a máxima da primeira hora, a **mínima** dessa hora
está a ~4,4 ATR de distância — um stop enorme. O teto de 2,5 ATR é o que impede a versão de aceitar
essas operações, e ele está fazendo o trabalho para o qual foi congelado: o pedágio medido ficou em
**0,1428 R** de média (máximo 0,2221 R), **abaixo do teto aritmético de 0,3333 R** calculado na
T3.33c e muito abaixo dos 0,6152 R da coorte da `volume_anomaly v2`. **O custo não é a causa da
perda aqui** — a expectancy já é negativa **antes** de qualquer custo (−0,0501 R bruta).

**Onde o resultado mora:** 10 stops (−11,03 R), 2 alvos (+3,30 R) e 8 saídas por horizonte
(+3,87 R). Com 2 alvos em 20, o equilíbrio de 44,5 % projetado na tabela de geometria **não** foi
alcançado nem de longe (10 %); o que segurou a coorte perto de −0,19 R por operação foram as saídas
por tempo, positivas. ETHUSDT sozinho responde por −2,50 R em 3 decisões.

**Critérios de morte (`notes-T3.33.md` §5.1):**

| K | condição | medido | dispara? |
|---|---|---|---|
| K1 | < 20 decisões | **exatamente 20** | **não — por uma decisão** |
| K2 | > 1 500 decisões | 20 | não |
| K3 | ≥ 100 avaliáveis **e** ≥ 30 dias **e** expectancy bruta (`r_ex_funding`) < 0 | 20 avaliáveis (< 100), 9 dias (< 30), `r_ex_funding` **−0,1930** | **não** (as duas primeiras condições faltam; a terceira já está cumprida) |
| K4 | `unavailable` > 40 % das barras | **1,98 %** (236/11 904) | não |
| K5 | cobertura de `R_net` < 70 % | **100 %** | não |
| — | regra dos 70 % (esta página) | máx. 35 % | não |

**Result: inconclusivo.** Nenhum critério de descarte dispara, e nenhum dispara **por pouco**: K1
falha por uma decisão e K3 tem duas de três condições ausentes. Mas a leitura honesta é que a
**única** condição de K3 que depende do mercado — expectancy bruta negativa — **já está cumprida**,
e que o rótulo de sessão, que é a hipótese inteira, não se distinguiu. **Next Action:** deixar a
versão correndo em `prospective` (ela já está no roster, `research_only`, sem carteira) e reavaliar
quando houver ≥ 100 avaliáveis e ≥ 30 dias — momento em que K3 decide sozinho. **Não** derivar
variante por sessão: escolher a melhor das três depois de ver as três é o data snooping que esta
mesma página proíbe.

#### Passada de estresse (T3.36) — coorte `replay:3fb9dda2…`, `as_of` 2026-09-08T19:53:28,833572Z

| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ |
|---|---|---:|---:|---:|---:|---|
| `base` | reprecificação | 20 | −0,1928 | 0,6616 | — | — |
| `custos_x2` | reprecificação | 20 | −0,3186 | 0,4966 | −0,1258 | [−0,1522; −0,1107] |
| `stop_x0.75` | reprecificação | 20 | −0,1581 | 0,7565 | +0,0347 | [−0,1077; +0,1749] |
| `stop_x1.25` | reprecificação | 20 | −0,2338 | 0,5632 | −0,0410 | [−0,1187; +0,0058] |
| `alvo_x0.75` | reprecificação | 20 | −0,1439 | 0,7455 | +0,0489 | [−0,0933; +0,2632] |
| `alvo_x1.25` | reprecificação | 20 | −0,1497 | 0,7373 | +0,0431 | [+0,0000; +0,1297] |
| `entrada_mais_1_barra` | reprecificação | 20 | −0,1978 | 0,6572 | −0,0050 | [−0,0674; +0,0659] |
| `sem_binance:DOGEUSDT` | recorte | 13 | −0,3014 | 0,5091 | — | — |
| `sem_binance:ETHUSDT` | recorte | 17 | −0,0797 | 0,8476 | — | — |
| `sem_binance:SOLUSDT` | recorte | 16 | −0,2306 | 0,5995 | — | — |
| `sem_binance:XRPUSDT` | recorte | 14 | −0,1860 | 0,6782 | — | — |
| `1a_metade_ate_2026-08-28` | recorte | 18 | −0,2293 | 0,6349 | — | — |
| `2a_metade_apos_2026-08-28` | recorte | 2 | +0,1361 | 4,1269 | — | — |

**Veredito da passada: `amostra_insuficiente`** — 20 desfechos avaliáveis de 30 exigidos. A tabela é
**descritiva**, não um veredito de robustez: nenhuma linha dela deve ser citada como "frágil a X" ou
"robusto a X". A segunda metade tem **duas** operações; o `+0,1361 R` dela não é informação.

Fonte (comandos e saídas verbatim): `.claude/state/notes-T3.33g.md`.

### 2026-09-08 — tentativa de ativação **PARADA antes de qualquer escrita** (T3.33f)

Não é uma avaliação: é o registro datado de que o experimento **não começou**, e por quê.

O `code_ref` existe e a imagem publicada o carrega — `docker exec hunter-strategy-worker-1 python -c
"import hunter_core.strategies.session_orb_v1"` responde `import ok session_orb_v1 v1` em
`hunter-api:cf51c7d`. O que não existe é a **linha do catálogo**: em 2026-09-08 17:36 UTC a tabela
`strategies` não tem a chave `session_orb` (13 linhas em `strategy_versions`, nenhuma dela), então
`activate_strategy_version.py session_orb v1 --dry-run` não teria o que ativar e a corrida foi
**interrompida antes** de rodar — nada foi escrito, nem um `system_events` de recusa.

O passo que falta é do operador e é uma linha só:

```
docker exec hunter-api-1 python infra/scripts/seed.py
```

`seed.py` grava as tabelas de referência (entre elas `strategies` e os rascunhos `strategy_versions`)
e **não tem `--dry-run`** — a mesma pendência aberta na T3.33e (CONCERN 1 de `notes-T3.33e.md`).
Depois dele, a sequência congelada deste experimento é: dry-run conferindo o digest
`…session_orb_v1@sha256:a4d514ad…` → ativação → 10 min de vigia de capacidade → replay de 31 d em
duas fatias com uma coorte só.

**Result: não iniciado.** **Next Action:** o operador roda o `seed.py`; a ativação e o replay
continuam válidos como escritos no protocolo acima, sem mudança.

Fonte (comandos e saídas verbatim): `.claude/state/notes-T3.33f.md`.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| alvo fixo de 2 ATR | 2026-09-08 | recusado **antes** de rodar: com stop no dado, o ganho/risco varia de 4:1 a 1,3:1 | esta página, seção Geometria |
| versão por sessão única | 2026-09-08 | **não** derivada: as três sessões dividiram a amostra 30/35/35 % e as três perderam; escolher a melhor depois de ver as três é o data snooping proibido nesta mesma página | Avaliação (replay, dia um), T3.33g |
| afrouxar `range_risk_atr_max` acima de 2,5 | 2026-09-08 | **não** derivada: 277 das 279 recusas de geometria são por faixa larga (mediana 4,44 ATR); afrouxar o teto compraria amostra ao preço de stops de 4 ATR — exatamente o pedágio que este teto existe para conter | Avaliação (replay, dia um), T3.33g |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] · [[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Registro de Tentativas]]

## Fontes

`.claude/state/notes-T3.33.md` · `.claude/state/brief-T3.33c-session_orb_v1.md` ·
`infra/scripts/seed_reference.py` · `infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py`
