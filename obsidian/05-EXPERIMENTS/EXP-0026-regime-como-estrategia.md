---
tags: [experimento, regime, portao-de-elegibilidade, mean-reversion, momentum, 90-dias]
updated: 2026-09-10
status: avaliado
owner: quant-engineer
exp: EXP-0026
strategy: "mean_reversion + momentum"
version: "mean_reversion v15/v16/v17 (de v10) + momentum v11 (de v8)"
result: reprovada
evaluable: 1767
days: 47
last_eval: "2026-09-10"
---

# EXP-0026 — a vantagem é um regime, não uma estratégia?

> **Pré-registro escrito em 2026-09-10, 12:20–12:45 BRT (15:20–15:45 UTC), ANTES de qualquer replay
> dos braços.** Origem: brief T3.76 (`.claude/state/brief-T3.76-validacao-em-um-dia.md`), Everton
> 12:10 BRT — "90 dias é muita coisa, precisamos validar dentro de 1 dia". Continuação direta de
> [[EXP-0025-mean-reversion-90-dias|EXP-0025]] (a família é negativa em 90 d e positiva só em
> agosto–setembro) e de [[EXP-0020-regime-gate|EXP-0020]] (o portão existe desde a `0017` e **nunca
> tinha sido replayado**, porque a série horária de regime não existia para a janela). Nada aqui é
> dinheiro real; nenhuma versão é ativada, promovida ou aposentada por esta página.

## O bloqueio que esta tarefa teve de tirar do caminho primeiro

O portão de elegibilidade trata **hora sem linha como inelegível** (`regime_gate:unknown`,
`docs/PIPELINE.md` §4b item 10). Às 12:05 BRT de 2026-09-10 a série `market_regimes`
(`scope = btc`, `classifier_version = regime_hourly_v1`) tinha **784 linhas** cobrindo
**36,3 %** das 2 161 horas dos 90 dias — e 205 dessas linhas eram `UNKNOWN` de aquecimento,
escritas em 2026-09-08 quando `candles` só ia até 2026-08-08. Um braço com portão medido sobre
essa série teria ficado mudo em dois terços da janela **por falta de dado**, e o Δ contra o pai
seria medido sobre quase nada.

O reparo profundo (`regime_hourly --once --repair-days 90`, o botão de operador do §4b item 7)
foi rodado em três passadas às 12:12–12:13 BRT: **1 320 horas inseridas, 841 atualizadas, e a
terceira passada escreveu 0** (idempotência pela chave e pelo digest). Cobertura depois:
**2 161/2 161 = 100 %**, 0 hora duplicada. As **205** horas que continuam `UNKNOWN` são
`trend_warmup` e são propriedade do **dado**, não do produtor: a vela de 1 min do BTC começa em
2026-06-11 19:00Z e a tendência exige 224 horas contíguas atrás, então a primeira hora que **pode**
sair classificada é 2026-06-21 04:00Z. Toda a janela J1 até essa hora é inelegível para qualquer
braço com portão, e isso está declarado aqui **antes** do resultado.

Distribuição das horas depois do reparo (`infra/scripts/sql/research/2026-09-10-t376-q02-*.sql`):

| janela | horas | SIDEWAYS | LOW_VOL | HIGH_VOL | BTC_BULL | BTC_BEAR | UNKNOWN |
|---|---:|---:|---:|---:|---:|---:|---:|
| J1 06-12→07-12 | 705 | 92 | 43 | 121 | 145 | 99 | **205** |
| J2 07-12→08-11 | 720 | 221 | 59 | 40 | 264 | 136 | 0 |
| J3 08-11→09-10 | 720 | 192 | 50 | 176 | 118 | 184 | 0 |
| **total** | **2 145** | **505** | **152** | **337** | **527** | **419** | **205** |

## Hipótese (congelada)

**A vantagem que a [[EXP-0025-mean-reversion-90-dias|EXP-0025]] achou só em agosto–setembro é um
regime, não uma estratégia.** Se for verdade, restringir a elegibilidade da `mean_reversion v10`
aos regimes de **consolidação** (`SIDEWAYS`, `LOW_VOLATILITY`) recupera expectativa positiva sobre
os 90 dias inteiros; e restringi-la ao regime **oposto** (`HIGH_VOLATILITY`) piora. A hipótese
espelhada para o momentum vem da [[KB-0079-onde-ganha-e-perde|KB-0079]]:
o momentum só ganha em `HIGH_VOLATILITY`, e `momentum v11` (já derivada, portão
`btc:BTC_BULL,HIGH_VOLATILITY`) nunca foi medida em 90 dias.

## Braços (congelados)

| braço | pai | portão (`eligibility_policy`) | papel |
|---|---|---|---|
| `mean_reversion v15` | `v10` | `regime=btc:SIDEWAYS,LOW_VOLATILITY` | hipótese principal (consolidação) |
| `mean_reversion v16` | `v10` | `regime=btc:SIDEWAYS` | a mesma hipótese, mais estreita |
| `mean_reversion v17` | `v10` | `regime=btc:HIGH_VOLATILITY` | **falseamento** — esperado **pior** |
| `momentum v11` | `v8` | `regime=btc:BTC_BULL,HIGH_VOLATILITY` (já existe, `active`) | hipótese da KB-0079 |

**Controle pré-declarado:** o **pai**, na mesma janela e nos mesmos 16 mercados. Para a
`mean_reversion` o controle já existe e não será re-rodado: coorte
`replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3` (798 decisões, 89 dias, T3.62b). Para o `momentum` o
controle **não existe em 90 dias** e tem de ser produzido: `momentum v8` na mesma janela.
Nenhum braço parte de v10 do momentum (aposentada em 2026-09-09 por C5).

**Janela:** `2026-06-12T00:00Z → 2026-09-10T00:00Z`, fronteiras `06-12 / 07-12 / 08-11 / 09-10`.
**Universo:** os 16 mercados do Lab — ARB BNB BTC DASH DOGE ETH LINK NEAR PROM SAHARA SOL SUI TAO
UNI XRP ZEC — em 4 fatias de 4. **Eixo primário:** `r_ex_funding` (o mesmo da EXP-0025; 498 dos 798
desfechos do pai são `NULL` em `r_multiple` por `funding_schedule_unknown`). **Custos assumidos:**
spread 2 bps, slippage 5 bps/lado, taxa 4 bps/lado, `max_entry_delay_s = 120`.
**Bootstrap:** blocos de dia inteiro, `t362b/blocos90.py`.

## Regra de sucesso — e a correção que o desenho do brief exigiu

O brief pediu: *"Δ pareado por (mercado, barra) contra o pai sobre as barras elegíveis
compartilhadas ≥ +0,05 R, IC 95 % por blocos de dia acima de zero, n ≥ 100, positivo em ao menos 2
das 3 janelas de 30 d, e leave-one-market-out nunca negativo"*. **Quatro dessas cinco condições
valem como estão. A primeira, como escrita, mede zero por construção** e isso precisa estar no
pré-registro, não no rodapé do resultado:

> um portão de elegibilidade **não muda a decisão** numa barra elegível — ele só **remove barras**.
> Sobre as barras elegíveis compartilhadas, filha e pai leem o mesmo contexto, o mesmo código
> congelado e os mesmos parâmetros, então o Δ pareado é **0 R** exceto pela divergência de máquina
> de estados do slot descrita em `docs/PIPELINE.md` §4b item 11 (`INELIGIBLE` não arma a barreira,
> logo a filha pode abrir um episódio numa barra que o pai nunca considerou). Essa divergência é
> um **artefato de contabilidade**, não uma vantagem: medir "o Δ pareado" seria medir o ruído do
> slot e chamá-lo de edge.

A quantidade que a hipótese realmente afirma é **condicional contra incondicional**: a expectativa
do pai **dentro** do conjunto de horas permitido, contra a expectativa do pai em **todas** as horas.
Ela é por natureza **não pareada** (as duas populações não compartilham barras), e é exatamente o
contraste que a EXP-0025 já usou para J3 − J1J2. Congelado, então, para os quatro braços:

**Δ = média de `r_ex_funding` das decisões do braço − média de `r_ex_funding` das decisões do pai
na janela inteira**, com IC 95 % por **bootstrap de blocos de dia inteiro, não pareado**
(20 000 reamostragens, semente `20260910`, a mesma da EXP-0025).

**Aprova** quem cumprir **todas**:

1. Δ ≥ **+0,05 R** e o IC 95 % por blocos de dia **acima de zero**;
2. **n ≥ 100** desfechos avaliáveis **e** ≥ 30 dias distintos (régua editorial do Lab);
3. média de `r_ex_funding` **positiva em ao menos 2 das 3 janelas** de 30 dias;
4. **leave-one-market-out nunca negativo** (16 reajustes, um por mercado retirado);
5. o Δ pareado por (mercado, barra) sobre as barras elegíveis compartilhadas fica **dentro de
   ±0,02 R de zero** — não como prova de vantagem, e sim como **prova de que o portão é só um
   portão**: um Δ pareado grande significaria que a filha está decidindo diferente do pai numa
   barra em que ambos são elegíveis, o que só pode ser divergência de slot (item 11) ou bug.

**Qualquer coisa a menos = `descartar`**, e a versão é aposentada pela via auditada
(`activate_strategy_version.py --deprecate`) no mesmo dia — regra permanente do Everton ("as que
estão dando ruim pode matar"). **Um braço mudo** (n < 100) é `descartar por população`, nunca
"negativo": é ausência de amostra, não ausência de vantagem.

**Falseamento:** se `v17` (`HIGH_VOLATILITY`, o braço que deveria ser o pior) **aprovar** e
`v15`/`v16` não, a hipótese "consolidação" está **refutada** e o que sobra é uma hipótese nova —
"a vantagem vive na volatilidade alta" — que **não** pode ser declarada vencedora nesta página:
ela nasce como candidata da EXP seguinte, com pré-registro próprio e prospectivo próprio.

**Replicação:** os **12 mercados que não escolheram a `v10`** (T3.62: `s2`–`s4`, tudo menos
ETH/SOL/XRP/DOGE) são reportados **separadamente** dos 4 originais em todos os braços.

**Prospectivo:** o braço que aprovar abre coorte `prospective` de 30 dias **no mesmo dia**, em
paralelo — nunca depois, nunca no lugar do replay.

## O que já se sabe ANTES de rodar — e por que isto é exploratório, não confirmatório

A série de regime agora cobre os 90 dias, então dá para cortar a coorte do **pai** (`v10`, 798
decisões já em disco) pelo rótulo que o portão usaria, **sem rodar nada**
(`infra/scripts/sql/research/2026-09-10-t376-q03-coorte-v10-por-regime.sql`, `read_at`
2026-09-10 15:20:01Z). Isto é a **estimativa declarada de `n`** de cada braço e a expectativa de
sinal — e é **in-sample**: é o mesmo dado que gerou a hipótese. Está escrito aqui **antes** do
replay porque esconder um número que já foi visto é pior que declará-lo.

| rótulo da hora | decisões do pai | dias | média `r_ex_funding` | soma R | PF |
|---|---:|---:|---:|---:|---:|
| `HIGH_VOLATILITY` | 218 | 21 | **+0,0568** | +12,37 | 1,202 |
| `BTC_BULL` | 166 | 30 | −0,1239 | −20,58 | 0,669 |
| `SIDEWAYS` | 159 | 28 | +0,0335 | +5,33 | 1,128 |
| `BTC_BEAR` | 140 | 23 | −0,0481 | −6,73 | 0,864 |
| `UNKNOWN` | 72 | 10 | **−0,1837** | −13,22 | 0,604 |
| `LOW_VOLATILITY` | 43 | 11 | −0,0122 | −0,52 | 0,959 |
| **pai, todas as horas** | **798** | **89** | **−0,0293** | **−23,35** | 0,910 |

Três leituras, todas registradas antes do resultado:

1. **A expectativa de `n` fecha a régua nos três braços de `mean_reversion`** (202 / 159 / 218
   decisões do pai no conjunto de cada um, contra o mínimo de 100). O braço não nasce mudo — o que
   era o risco número um depois de `mean_reversion v11` (portão `SIDEWAYS` sobre a `v6`) ter sido
   aposentada em 2026-09-09 com **1 decisão em 31 d**. A diferença é o pai: a `v10` decide em 1 h e
   tem população, a `v6` decide em 15 min com ATR de 15 m e não tinha.
2. **O braço de falseamento já aparece como o melhor.** `HIGH_VOLATILITY` (+0,0568 R, PF 1,202) é
   o rótulo mais lucrativo do pai, e os dois braços de consolidação vêm depois
   (`SIDEWAYS` +0,0335, `LOW_VOLATILITY` −0,0122). Se o replay confirmar, a hipótese do brief está
   **invertida** — e o desenho acima já diz o que isso autoriza e o que não autoriza.
3. **`HIGH_VOLATILITY` é candidato a ser um disfarce de calendário.** As 337 horas
   `HIGH_VOLATILITY` dos 90 dias estão concentradas em J3 (176) e J1 (121), e o desempenho do pai
   nelas é J1 −0,1064 / J2 +0,0288 / J3 **+0,1985** — a mesma assinatura "agosto era a história
   inteira" da EXP-0025. `SIDEWAYS` é o único rótulo distribuído de forma parecida entre as três
   janelas (92/221/192 horas) com sinal J1 +0,1495 / J2 −0,0424 / J3 +0,0366. **A condição 3 da
   régua de sucesso existe exatamente para separar as duas coisas**, e é por isso que ela foi
   escrita antes destes números serem lidos (brief T3.76, 12:10 BRT).

**O que o replay dos braços acrescenta que este corte não dá:** a população **real** da filha
(item 11: a lista de decisões dela **não** é subconjunto da do pai), o funil K1–K6 sobre a coorte
dela, o `--stress`, o C5 e a leitura de leave-one-market-out sobre a coorte própria. O corte acima
é a melhor estimativa disponível de graça e **não** substitui nada disso.

## Portão de desenho (C1–C8)

**Não aplicável como portão novo.** Nenhum braço muda parâmetro ou código: os quatro herdam o
conjunto congelado do pai byte a byte e mudam **apenas** `eligibility_policy`. Os portões vivem nas
páginas onde as famílias nasceram — [[EXP-0009-mean-reversion-pullback-em-tendencia|EXP-0009]]
(`REVISE`, 65,5) e [[EXP-0001-momentum-v1|EXP-0001]]. Dois critérios, porém, **mudam de valor** com
o portão e ficam registrados aqui:

- **C3 (adequação da amostra):** o portão corta a frequência. Estimativa declarada acima — 202 /
  159 / 218 decisões do pai em 90 dias × 16 mercados, ou ~9 / ~7 / ~10 por mercado por 90 dias.
- **C4 (dependência de regime):** este experimento **é** C4. O que ele não pode fazer é usar o
  resultado como prova de que a família passa a ser independente de regime — ela passa a ser
  **explicitamente** dependente dele, o que é uma tese diferente e mais frágil.

Além disso, `docs/PIPELINE.md` §4b item 12: **K4 deixa de ser mensurável** numa versão com portão
(uma barra sem contexto é recusada como `ineligible` antes da checagem de contexto, e a filha mede
`unavailable ≈ 0` como falso verde). **K4 dos braços é lido no pai**, na mesma janela, e a fração
`ineligible` da filha é reportada como número próprio, nunca no lugar de K4.

## Protocolo (congelado — nunca editar)

- **Strategy / versões:** `mean_reversion` `v15`/`v16`/`v17`, derivadas de `v10`
  (`params_hash = d4fcf66f9449`, `code_ref …239dadc3f0bd395f`); `momentum` `v11`, derivada de `v8`
  (`params_hash = 69152dbc9173`).
- **Parâmetros:** idênticos aos do pai, byte a byte (`derive_variant.py` sem `--set`).
- **Portão:** `eligibility_policy`, regra `regime`, `rule = previous_closed_hour`,
  `scope = btc`, `classifier_version = regime_hourly_v1` — **a última hora fechada antes do corte**
  (`end_time <= source_bar_close`), §4b item 10.
- **Série de regime:** `market_regimes`, `scope = btc`, `classifier_version = regime_hourly_v1`,
  2 161/2 161 horas da janela, produzida por `regime_hourly --once --repair-days 90` em
  2026-09-10 15:12–15:13Z, idempotência provada (terceira passada: 0 escritas).
- **Timeframe de decisão / de outcome:** 15 min / 1 min (as quatro versões decidem em 15 min).
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com
  `entry_bar_open − source_bar_close ≤ 120 s`.
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra → stop;
  horizonte 4 h da entrada.
- **Política de reentrada:** um acompanhamento por `(strategy_version_id, market_id, cohort)`.
- **Cohort:** `replay:<run_id>` por braço, uma por versão, 12 fatias (3 janelas × 4 mercados).
- **Data de início:** 2026-09-10.

## Avaliações (acrescentadas, nunca reescritas)

### Pré-registro de 2026-09-10 — `as_of = 2026-09-10T15:45:00Z`

Nenhuma avaliação ainda. Estado: série de regime reparada e provada (100 % de cobertura,
idempotente), regra de sucesso congelada, expectativa de `n` declarada, braço de falseamento
declarado como já aparecendo melhor que a hipótese principal no corte in-sample do pai.
**Result:** `nao-iniciado`. **Next Action:** derivar `v15`/`v16`/`v17` (ensaio primeiro), ativar
`research_only` pela via auditada, replayar os quatro braços + o controle `momentum v8` em fatias
de ≤ 4 mercados × ≤ 31 d, estressar os sobreviventes e escrever o veredito por braço aqui,
acrescentando — nunca reescrevendo esta seção.

### Avaliação de 2026-09-10 — `as_of = 2026-09-10T18:11:00Z`

**Corridas:** 48 fatias de replay (`mean_reversion v15`/`v16`/`v17` e `momentum v11`, 12 cada),
**552 960 barras**, **0 erros**, coortes `replay:3271f431…` / `replay:309144d2…` /
`replay:095d4772…` / `replay:70f55430…`, janelas `06-12 → 07-12 → 08-11 → 09-10`, 4 fatias de 4
mercados cada, `--explain-ledger` por fatia. Controle da `mean_reversion`: `replay:c7d138eb…`
(T3.62b, não re-rodado). Comandos e saídas verbatim em `.claude/state/notes-T3.76.md`.

**Cobertura (contagens completas, eixo `r_ex_funding` presente em 100 % da população):**

| versão | decisões | terminais | dias | `R_net` | K4 (do pai) | `ineligible` | erros |
|---|---:|---:|---:|---:|---:|---:|---:|
| `v10` (pai) | 798 | 798 | 89 | 37,6 % | **0,93 %** | 0 % | 0 |
| `v15` | 209 | 209 | 35 | 100 % | ler no pai | 69,6 % | 0 |
| `v16` | 169 | 169 | 30 | 100 % | ler no pai | 76,6 % | 0 |
| `v17` | 222 | 222 | **21** | 100 % | ler no pai | 84,4 % | 0 |
| `momentum v11` | 1 167 | 1 167 | 47 | 99,7 % | — | 60,0 % | 0 |

`R_net` cobre 100 % dos braços e só 37,6 % do pai: as coortes de hoje nasceram **depois** do
backfill de funding da T3.75 e a do pai é anterior a ele (`signal_outcomes` é append-honesto, T3.75
§3). É exatamente por isso que o eixo pré-registrado é `r_ex_funding` — os dois eixos coincidem nos
braços (diferença de 0,001 R).

**A régua, condição por condição:**

| braço | 1. Δ ≥ +0,05 e IC > 0 | 2. n ≥ 100 e ≥ 30 d | 3. 2 de 3 janelas | 4. LOO nunca negativo | 5. Δ pareado ≈ 0 | estresse | **veredito** |
|---|---|---|---|---|---|---|---|
| `v15` | **FALHA** — +0,0651, IC [−0,0832; +0,2024] | PASSA (209 / 35) | PASSA (2/3) | PASSA (0 de 14) | PASSA (**+0,0000**) | frágil a custos; dependente de metade | **`descartar`** |
| `v16` | **FALHA** — +0,0744, IC [−0,1135; +0,2362] | PASSA (169 / 30) | PASSA (2/3) | PASSA (0 de 14) | PASSA (**+0,0000**) | frágil a custos | **`descartar`** |
| `v17` | **FALHA** — +0,0905, IC [−0,1540; +0,2763] | **FALHA** (222 / **21 d**) | PASSA (2/3) | PASSA (0 de 16) | PASSA (**+0,0000**) | frágil a custos; dependente de metade | **`descartar`** |
| `momentum v11` | **não computável** — o controle `momentum v8` está `deprecated` e o replay recusa versão não executável | PASSA (1 167 / 47) | **FALHA** (1/3) | **FALHA** (16 de 16 negativos) | n/a | **`sem_vantagem_na_base`** | **`descartar`** |

**Expectativa por braço (eixo `r_ex_funding`, IC 95 % por blocos de dia, 20 000 reamostragens,
semente 20260910):**

| versão | n | dias | média | soma R | PF | IC 95 % da média |
|---|---:|---:|---:|---:|---:|---|
| `v10` (pai) | 798 | 89 | −0,0293 | −23,35 | 0,910 | [−0,1336; +0,0728] |
| `v15` | 209 | 35 | **+0,0359** | +7,50 | 1,134 | [−0,1211; +0,1810] |
| `v16` | 169 | 30 | **+0,0451** | +7,62 | 1,175 | [−0,1528; +0,2140] |
| `v17` | 222 | 21 | **+0,0613** | +13,60 | 1,223 | [−0,2346; +0,2999] |
| `momentum v11` | 1 167 | 47 | **−0,0595** | −69,43 | 0,815 | [−0,1518; +0,0402] |

**Por janela de 30 d (condição 3):** `v15` +0,1121 / −0,0668 / +0,0730 · `v16` +0,1542 / −0,0383 /
+0,0528 · `v17` −0,1091 / +0,0288 / +0,2073 · `momentum v11` −0,1101 / −0,2137 / +0,0931 · pai
−0,1216 / −0,0919 / +0,1155.

**C5 (risco/entrada acima do teto de 3 % do `paper_v1`):** `v15` 14,4 % · `v16` 14,2 % ·
`v17` **22,5 %** · `momentum v11` 14,9 % · pai 16,8 %. O braço de volatilidade alta é o que mais
pede stop fora da banda da carteira — coerente com o rótulo e mais uma razão para ele não ser
promovido sem desenho próprio.

**Replicação (4 mercados originais × 12 novos, pareado por dia):** `v15` +0,2104 × +0,0031
(Δ +0,2073, IC [−0,0415; +0,4629]) · `v16` +0,2293 × +0,0101 (Δ +0,2192, IC [−0,0576; +0,4837]) ·
`v17` +0,0315 × +0,0704 (Δ −0,0389, IC [−0,2185; +0,1258]). Nos dois braços de consolidação **toda a
expectativa está nos 4 mercados que geraram a hipótese**, e os 12 que não a escolheram medem
praticamente zero; o IC não exclui zero em nenhum caso, mas a direção é a mesma da T3.62.

**Result:** **refutou**. **Conclusion:** o portão de regime está correto e faz exatamente o que
promete — o Δ pareado por (mercado, barra) contra o pai é **0,0000 R** nos três braços, e cada braço
decide **só** dentro do rótulo pedido (`v15` SIDEWAYS=166 + LOW_VOLATILITY=43; `v16` SIDEWAYS=169;
`v17` HIGH_VOLATILITY=222). Ele move o ponto de −0,029 R para +0,036…+0,061 R. **E o intervalo não
exclui zero em nenhum braço**, porque o portão compra expectativa pagando em **dias**: 21 a 35 blocos
de dia produzem IC de ±0,15 a ±0,25 R, e não há corte de rótulo que devolva calendário. A hipótese do
brief — "a vantagem é a consolidação" — está **refutada pelo próprio braço de falseamento**:
`HIGH_VOLATILITY`, pré-registrado como o pior, tem o maior ponto e o maior PF. E ele é o mais
suspeito de todos: 176 das suas 337 horas estão em agosto–setembro, o estresse mede 1ª metade
−0,0960 contra 2ª metade +0,2000, e o C5 dele é o maior. Nada aqui autoriza declarar "a vantagem
vive na volatilidade alta" — isso é uma EXP nova, com pré-registro e prospectivo próprios.

**Next Action:** aposentar `v15`, `v16`, `v17` e `momentum v11` pela via auditada
(`activate_strategy_version.py --deprecate`). **Não executado por esta tarefa** e o motivo está
registrado: às 13:45 BRT de 2026-09-10 o HEAD de `/opt/project-hunter` foi para `60f3fe6`, um commit
sem imagem construída, e `compose.sh ops` recusa rodar por desenho (T3.15e, achado F2) — as quatro
versões seguem **`active`** e decidindo na faixa viva até alguém rodar as quatro linhas listadas em
`.claude/state/notes-T3.76.md` §7. **Nenhuma coorte `prospective` foi aberta de propósito**: a regra
do dia manda começar o prospectivo de 30 d no mesmo dia em que um candidato **passa**, e nenhum
passou.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `mean_reversion v11` (portão `SIDEWAYS` sobre `v6`) | 2026-09-09 | primeira tentativa do mesmo portão, sobre um pai de 15 min | aposentada 16:07:43Z — 1 decisão em 31 d (K1); série de regime cobria só ~33 dias |
| `momentum v12`/`v13`, `mean_reversion v12`/`v13` | 2026-09-09 | portão de **horas** (T3.59) somado ao de regime | aposentadas 19:13Z |

## Relacionadas

[[Experiments Index]] · [[EXP-0025-mean-reversion-90-dias]] · [[EXP-0020-regime-gate]] ·
[[EXP-0021-timeframe]] · [[Strategies]] · [[Strategy Performance]]

## Fontes

`.claude/state/brief-T3.76-validacao-em-um-dia.md` · `.claude/state/notes-T3.76.md` ·
`.claude/state/notes-T3.62b.md` · `docs/PIPELINE.md` §4b (itens 7, 10, 11, 12, 13) e §6c ·
`infra/scripts/sql/research/2026-09-10-t376-q00-cobertura-regime-e-velas.sql` ·
`infra/scripts/sql/research/2026-09-10-t376-q01-custo-da-leitura-do-universo.sql` ·
`infra/scripts/sql/research/2026-09-10-t376-q02-cobertura-depois-do-backfill.sql` ·
`infra/scripts/sql/research/2026-09-10-t376-q03-coorte-v10-por-regime.sql`
