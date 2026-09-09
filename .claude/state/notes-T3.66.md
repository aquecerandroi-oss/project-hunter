# T3.66 — o controle contrarian lag-1 da `mean_reversion` (EXP-0024)

**Papel:** quant-engineer. **Data:** 2026-09-09, 16:38–17:20 de Brasília (19:38–20:20 UTC).
**Natureza:** pesquisa. VPS **somente leitura**, nada ativado, nada depreciado, **nada commitado**.

Pergunta do plantão (H-P1a/H-P1b em `obsidian/00-INBOX/Hipoteses-do-plantao.md`, a partir de
`obsidian/11-KNOWLEDGE/KB-0082-…` e do parecer da Astra em
`.claude/state/astra-review-plantao-20260909-1700.md`): **o edge da família `mean_reversion` é mais
do que "reversão da última barra de 15 m"?**

Pré-registro e resultado completos: `.claude/state/exp-drafts/EXP-0024-controle-contrarian.md`.
Esta nota registra o *como* e as decisões de método que não cabem lá.

---

## 1. A ordem dos atos, que é o que dá valor ao resto

1. **19:42Z** — `q00`, só metadado de desenho (parâmetros congelados das 14 versões e **contagens**
   por versão/coorte/estado). Nenhum R, nenhum retorno.
2. **19:49Z** — o pré-registro escrito e fechado (`EXP-0024`), com hipóteses, população, os dois
   controles, a métrica, os testes, a régua de multiplicidade, a régua editorial e — deliberadamente
   — a **degenerescência de C1 declarada antes de medir**.
3. **19:50Z** — `q01`/`q02` exportam população e velas.
4. **19:55–20:00Z** — TDD do estimador e do controle (14 provas sintéticas), depois a medição.
5. **20:03Z** — `q03` confere que a população congelada não se moveu desde a exportação.

## 2. Três decisões de método que valem mais que os números

### 2.1 Não existe um segundo caminho de saída

Toda operação hipotética deste trabalho — decisão, C1 e C2 — termina em
`hunter_strategy_worker.walker.walk` e `pricing.r_net`, o **mesmo código congelado** que decidiu e
liquidou a população. Cheguei a desenhar o caminhar em SQL (transferência ~200× menor) e desisti: uma
reimplementação das regras de saída teria liberdade para discordar da população que ela tenta
explicar. O preço foi transferir 1,23 milhão de velas de 1 min (12,8 MB gzipados, 19,5 s) e caminhar
em Python. Valeu: **a validação saiu exata**.

`walk` é um fold resumível, então `rodar.caminhar_em_levas` alimenta o plano em levas de 30 min e
para quando o desfecho fecha — sem isso seriam 241 `Bar` com quatro `Decimal` cada para um stop que
disparou no quinto minuto.

### 2.2 A validação é o portão, não um apêndice

Critério congelado *antes*: 100 % de igualdade de `result` **e** `|ΔR| ≤ 1e-6` contra o que
`signal_outcomes` persistiu, senão nada abaixo pode ser lido. Resultado:

```
validação: 621 recaminhadas | sem velas/censuradas 0 | divergências 0 | max |ΔR| 0.000e+00
```

Zero exato em 621 decisões. Isso prova de uma vez o dado (as velas persistidas), o plano (níveis de
`agent_signals` + `entry_bar_open` do envelope), a máquina de saída e a aritmética de custo.

Detalhe que a validação revelou e que o desenho tinha de absorver: **32 das 621 decisões entraram em
`barra + 2 min`**, não `barra + 1 min` (fila da faixa viva; o replay é sempre +1). O controle entra
sempre em `+1 min`, como o pré-registro manda — e é por isso que C1 diverge da decisão em 3 dos 248
casos concordantes em vez de 0.

### 2.3 C1 é degenerado, e isso foi dito antes, não depois

O brief pedia um controle "na mesma barra, mesma geometria, mesmos custos". Segurando mercado,
barra, entrada, geometria, saída e custo, **a única coisa que sobra variando é qual barra a regra
escolhe** — então, quando C1 dispara, ele *é* a operação da decisão e `Δ ≡ 0`. Medido: **245 de 248**
com `|Δ| < 1e-9`.

Registrei isso no pré-registro (§C1) com a consequência: `Δ1` não mede "edge incremental" no sentido
usual; ele mede **quanto do R da família vem de barras que um lag-1 teria pulado**. O teste
incremental de verdade é C2 — o segundo controle do brief —, e por isso publiquei também o **Holm
sobre os três `p`** (a família mais estrita) ao lado do Holm sobre os dois, para que a escolha da
família não possa ser lida como a escolha conveniente. Não muda nada: nada é significativo em
nenhuma das duas.

## 3. O que a medida diz (resumo; a íntegra está no EXP-0024)

**O fato que responde a pergunta é descritivo e não depende de poder estatístico:**

| | agregado | v1 | v2 | v6 | v10 |
|---|---|---|---|---|---|
| decisões | 621 | 84 | 33 | 169 | 335 |
| dispara depois de barra de **baixa** | 39,9 % | 53,6 % | 48,5 % | 36,7 % | 37,3 % |

Taxa-base de barras de baixa na mesma grade e janela (56 perpétuos): **49,8 %**. Na mesma base
(sem dojis) a família mede **40,7 %**. Ela dispara depois de baixa **menos** vezes que o acaso —
**não é um contrarian lag-1 disfarçado; pende para o lado oposto**, o que é coerente com a regra
(z-score sobre o *nível*, não sobre a direção da barra, mais a estabilização `close ≥ meio`, que
empurra para a barra de repique).

**Os dois testes pré-registrados: inconclusivos, com o ponto do lado declarado.**

| | agregado | v10 (o maior recorte) |
|---|---|---|
| (a) Δ1 = R − C1 | +0,0735 [−0,0517; +0,1715] p 0,2250 | +0,0711 [−0,0464; +0,1793] p 0,2462 |
| (b) expectancy `r_ex_funding` | +0,1082 [−0,0836; +0,2873] p 0,2798 | +0,1264 [−0,0738; +0,3030] p 0,2208 |
| Holm(2) | 0,4500 / 0,4500 | 0,4416 / 0,4416 |
| (c) Δ2 = R − C2 | +0,1545 [−0,0489; +0,3493] p 0,1450 | +0,1408 [−0,0597; +0,3198] p 0,1766 |
| **expectancy do próprio C2** | **−0,0462 [−0,0765; −0,0159] p 0,0032** | −0,0143 [−0,0386; +0,0072] p 0,2012 |

**A linha que mais informa é a última:** o contrarian lag-1, com a nossa geometria, a nossa saída e
os nossos 20 bps, **perde** — −0,046 R por operação no agregado, IC que não cruza zero. "A família é
uma forma cara de comprar reversão da última barra" pressupõe que comprar reversão da última barra
seja rentável; no nosso dado, não é.

**E a afirmação do artigo replica** (todos os baldes de 15 min completos dos 56 perpétuos, bloco de
dia UTC): `P(próxima em alta | esta em baixa) = 0,5128 [0,5033; 0,5225]` contra
`P(próxima em alta | esta em alta) = 0,4907 [0,4813; 0,5006]`, +2,21 p.p. A previsibilidade
direcional existe **e não paga 20 bps** — as duas metades da KB-0082 se sustentam no nosso perpétuo,
e a cláusula de refutação da nota não dispara.

## 4. Ressalvas que não podem sumir do relatório

1. **Régua editorial (100 avaliáveis E 30 dias distintos): não cumprida por nenhuma versão.**
   `v10` 335 e **29** dias — falta **um**. `v6` 169/24, `v1` 84/11, `v2` 33/8. Só o agregado chega a
   31 dias, e ele conta a mesma `(mercado, barra)` mais de uma vez (621 decisões sobre **361** pares
   distintos, porque `v6` e `v10` diferem só no ATR). **`result: inconclusivo`.**
2. **A coorte prospectiva tem UM dia.** O bootstrap de blocos degenera: o IC colapsa no ponto e o `p`
   cai no piso `2/B`. Publiquei com o aviso em vez de omitir — `+0,1234` e `+0,2318` daquela linha
   **não são evidência**.
3. **A população se moveu durante a tarefa.** `v10` tinha 195 desfechos às 19:42Z e 335 às 19:47Z
   (uma corrida de replay terminando). O arquivo `t366/decisoes.csv` é a população de registro;
   `q03` (20:03:45Z) confirma que ela está estável desde a exportação. "Decisões congeladas" é
   verdade sobre um instante, não sobre a tabela — e isso vale para toda análise desta série.
4. **Funding fora dos dois lados.** O R primário é `r_ex_funding` porque o controle não tem cadência
   de funding computável sem reimplementar `funding.py` sobre barras hipotéticas. Medido, o funding
   custa **0,0006 R por decisão** nesta população (agregado `r_multiple` +0,1076 contra
   `r_ex_funding` +0,1082) — irrelevante perto dos 20 bps, mas registrado em vez de suposto.
   (D-P3/T3.65 investiga separadamente o falso zero de cadência nos nove TradFi que mudaram para 4 h;
   nenhum deles está nesta população.)
5. **O tercil de fluxo da KB-0082 continua não medido.** `|i| = |2·taker_buy/volume − 1|` exige
   carregar `taker_buy_volume` no `Bar` da agregação (`aggregate.py:40,77`). Declarado no
   pré-registro como fora de escopo; é a continuação natural.
6. **Uma janela só, sem confirmação fora da amostra.** Nada aqui confirma; o que é forte é o fato
   descritivo do §3, que não depende de significância.

## 5. Suposições numéricas que eu tive de fazer

| suposição | valor | por quê |
|---|---|---|
| custos do controle | `spread 2 / slippage 5 / fee 4` (20 bps ida e volta) | lidos do `default_parameters` das quatro versões em `q00`, não escolhidos |
| geometria do controle | `risco_pct` e `tr` **da decisão pareada** | é o que faz "mesmo stop/alvo" sobreviver a um preço diferente e mantém idêntica a identidade `custo_R = 0,0020/risco_pct` (KB-0076) |
| hora do dia do pareamento | **UTC** | é a grade em que o portão de horas e o regime horário já falam (PIPELINE §4b) |
| `K` do pool C2 | 20 sorteios por decisão, ordem md5(`signal_id`+`market_id`+`barra`) | congelado no pré-registro; efetivo medido 19,4 (mínimo 2, nenhuma decisão sem pool) |
| janela do pool C2 | toda a janela da população, sem cerca de ±N dias | o brief pede pareamento por mercado e hora do dia, só; cercar por proximidade é outro experimento |
| bloco do bootstrap | dia em **Brasília** da barra de origem | a convenção da T3.53/T3.42/T3.57b |
| preços em `float` para varrer, `Decimal(repr(x))` para caminhar | — | 1,2 M `Bar` com quatro `Decimal` não cabe em memória; a validação exata (max ΔR = 0) é a prova de que não custou precisão onde importa |
| doji (`close == open`) | não dispara o controle, contado à parte | 12 das 621 |

## 6. Arquivos

- `.claude/state/exp-drafts/EXP-0024-controle-contrarian.md` — pré-registro (fechado 19:49Z) + resultado.
- `.claude/state/exp-drafts/t366/blocos.py` — bootstrap por blocos de dia + Holm.
- `.claude/state/exp-drafts/t366/controle.py` — dobra de 15 min, sinal lag-1, planos, reuso de `walk`.
- `.claude/state/exp-drafts/t366/rodar.py` — validação + C1 + C2 + os testes.
- `.claude/state/exp-drafts/t366/descritivo.py` — reversão de sinal, expectancy do controle, cortes.
- `.claude/state/exp-drafts/t366/test_t366.py` — 14 provas sintéticas (oráculo).
- `.claude/state/exp-drafts/t366/decisoes.csv` (621) · `velas.csv.gz` (1 228 098) · `pareado.csv` (621).
- `infra/scripts/sql/research/2026-09-09-t366-q0{0,1,2,3}-*.sql` — as quatro leituras, todas em
  `repeatable read read only`.

## 7. Para a Sexta-feira (eu não editei `obsidian/**`)

- `Hipoteses-do-plantao.md`: H-P1a e H-P1b saem de "em brief (T3.66)" para **medidas e
  inconclusivas** — com a ressalva de que a *premissa* ("é só reversão da última barra") foi
  **refutada por descrição** (39,9 % / 40,7 % contra taxa-base 49,8 %).
- `KB-0082`: acrescentar a medição no nosso perpétuo (reversão de sinal +2,21 p.p., IC contra 0,50) e
  que o controle lag-1 mede **−0,046 R** a 20 bps — as duas metades do artigo replicam.
- `EXP-0009`: apontar para o EXP-0024 como diagnóstico, **sem editar o protocolo congelado**.
