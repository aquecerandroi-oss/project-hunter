---
tags: ["estrategia", "catalogo", "mean_reversion", "familia"]
strategy: mean_reversion
updated: 2026-09-12
---
# mean_reversion

<!-- generated:start -->
## Versões

| Versão | Propósito | Status | Veredito | Página |
|---|---|---|---|---|
| `v1` | `research_only` | `active` | **reprovada em 90 dias/16 mercados** (EXP-0025, T3.62b) — 542 avaliáveis, 83 dias; ex-funding **−0,0910 R**, PF 0,851, K3 disparado; estresse `frágil a custos`. Substitui a leitura de 31 dias abaixo. | [[mean_reversion-v1]] |
| `v2` | `research_only` | `active` | **reprovada em 90 dias/16 mercados** (EXP-0025, T3.62b) — 302 avaliáveis, 68 dias; ex-funding **−0,0343 R**, PF 0,940, K3 disparado; estresse `frágil a custos`. Substitui a leitura de 7 dias abaixo. | [[Estrategias/mean_reversion-v2|mean_reversion-v2]] |
| `v3` | `research_only` | `active` | inconclusivo, `REVISE` no portão — 11 avaliáveis, 4 dias; líquida +0,5131 R; corte de 70,3 % dispara a régua do `EXP-0006`. | [[Estrategias/mean_reversion-v3|mean_reversion-v3]] |
| `v4` | `research_only` | `deprecated` | descartar — K1 (10 decisões); aposentada 2026-09-08T23:34:57Z, sem sucessora. | [[mean_reversion-v4]] |
| `v5` | `research_only` | `deprecated` | descartar — K1 (9 decisões), 44 % fora da banda de stop do `paper_v1`; aposentada 2026-09-08T23:34:59Z, sem sucessora. | [[mean_reversion-v5]] |
| `v6` | `research_only` | `active` | manter em pesquisa — melhor candidata do eixo "stop largo" (guarda 95 % da economia de pedágio); K1 (15 decisões). | [[mean_reversion-v6]] |
| `v7` | `research_only` | `active` | manter em pesquisa com ressalva — só 32 % da economia de pedágio sobrevive; K1 (14 decisões). | [[mean_reversion-v7]] |
| `v8` | `research_only` | `active` | inconclusivo (sinal `negativo` no corpo do EXP) — Δ −0,2006 R contra `v6`; mantida pela mensurabilidade, não pelo mérito. | [[mean_reversion-v8]] |
| `v9` | `research_only` | `deprecated` | **efêmera, zero decisões** — variante do eixo de timeframe (`atr_timeframe` 1h, de `v6`), morreu por `atr_warmup`: pedia 5 820 min de contexto contra o teto de 1 560 do worker naquele instante; aposentada no mesmo turno (T3.54), sucessora `mean_reversion v10`. Sem página própria. | — |
| `v10` | `research_only` | `active` | **reprovada em 90 dias/16 mercados** (EXP-0025, T3.62b) — 798 avaliáveis, 89 dias; ex-funding **−0,0293 R**, PF 0,910, K3 disparado. Os +0,1105 R/PF 1,451 de 31 dias eram só a janela de agosto–setembro (Δ contra jun–ago exclui zero); os 4 mercados originais caem a +0,0002 R (zero) nos 90 d; C5 (teto de risco 3 %) 16,8 % em 90 d contra 32,3 % só em agosto. Sem página própria nesta sessão. | — |
| `v11` | `research_only` | `deprecated` | **portão de regime `btc:SIDEWAYS`, de `v6`** (G1 do [[EXP-0020-regime-gate]]) — morta no K1 (1 decisão em 31 dias, 4 mercados): `SIDEWAYS` só tem 6 h na primeira metade da janela de replay. `inconclusivo`, não negativo — as 14 decisões que o portão removeu do pai eram vencedoras (+0,2964 R), evidência **contra** a hipótese; aposentada 2026-09-09T16:07Z, sem sucessora. Sem página própria nesta sessão. | — |
| `v15` | `research_only` | `active` | **portão de regime `SIDEWAYS,LOW_VOLATILITY`, de `v10`** ([[EXP-0026-regime-como-estrategia]]) — `descartar`: Δ +0,0651 R, IC [−0,0832; +0,2024] (contém zero); estresse frágil a custos. Não aposentada nesta sessão (bloqueio de deploy, T3.76 §7). Sem página própria. | — |
| `v16` | `research_only` | `active` | **portão de regime `SIDEWAYS`, de `v10`** ([[EXP-0026-regime-como-estrategia]]) — `descartar`: Δ +0,0744 R, IC [−0,1135; +0,2362] (contém zero); estresse frágil a custos. Não aposentada nesta sessão (mesmo bloqueio). Sem página própria. | — |
| `v17` | `research_only` | `active` | **portão de regime `HIGH_VOLATILITY` (falseamento), de `v10`** ([[EXP-0026-regime-como-estrategia]]) — `descartar`: Δ +0,0905 R, IC [−0,1540; +0,2763] (contém zero); falha condição de dias (21 < 30); estresse frágil a custos, dependente de metade. Não aposentada nesta sessão (mesmo bloqueio). Sem página própria. | — |
| `v18` | `research_only` | `deprecated` | **portão de amplitude `breadth=0,10–0,60@breadth_v2`, de `v10`** ([[EXP-0027-amplitude]]) — `descartar`: Δ não pareado **−0,0184 R** contra o pai (sinal errado, IC [−0,1692; +0,1350]), 1 de 3 janelas positivas, LOMO negativo nos 16 mercados; condição 5 (Δ pareado por mercado-barra) confirma o portão em 0,0000 R; estresse `sem_vantagem_na_base`; cláusula de identidade dispara (corte por regime ≥ corte por amplitude). Aposentada **2026-09-12T01:15:24Z** (22:15 BRT), sem sucessora. Sem página própria. | — |
| `v19` | `research_only` | `deprecated` | **portão de amplitude `breadth=0,60–1,00@breadth_v2` (falseamento), de `v10`** ([[EXP-0027-amplitude]]) — `descartar`: Δ não pareado **+0,0372 R** (abaixo do piso de +0,05, IC [−0,1574; +0,2232]), 1 de 3 janelas positivas, LOMO negativo (sem DASHUSDT); condição 5 confirma o portão em 0,0000 R; estresse frágil a custos; cláusula de identidade dispara. Aposentada **2026-09-12T01:16:02Z** (22:16 BRT), sem sucessora. Sem página própria. | — |

## Ligações

- Convenção: [[Estrategias/README|Estratégias]]
- Eixo "teto de pedágio" (v1→v2/v3): [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]
- Eixo "stop largo" (v2→v6/v7, v3→v4/v5): [[EXP-0018-stop-largo]]
- Eixo "piso de ATR%" (v2→v8): [[EXP-0019-piso-atr]]
- Eixo "timeframe" (v6→v9/v10): [[EXP-0021-timeframe]]
- Eixo "portão de regime" (v6→v11): [[EXP-0020-regime-gate]]
- Replicação de 90 dias (v1/v2/v10): [[EXP-0025-mean-reversion-90-dias]]
- Eixo "portão de amplitude" (v10→v18/v19): [[EXP-0027-amplitude]]
- Eixo "portão de dispersão BTC × alts" (v10→v20/v21, **não derivadas** — `inviavel-populacao` em 2026-09-12): [[EXP-0029-dispersao-btc-alts]]
- Irmã de 1 h (módulo novo, código pronto, replay pendente): [[mean_reversion_h1]]
- Irmã de 5 min (módulo novo, ativada e **aposentada** em 2026-09-11: `descartar`, ex-funding −0,1940 R em 373 desfechos — e **o custo não foi a causa**, 89,8 % da piora é a vantagem bruta caindo de +0,1270 para +0,0346 R): [[mean_reversion_m5]] — [[EXP-0028-mean-reversion-5-min]]
<!-- generated:end -->


## Notas

**Tabela de versões corrigida e ampliada (`v1` estava marcada `draft`/sem veredito, desatualizada
desde a T3.33b) pela Sexta-feira em 2026-09-08**, a partir de
[[EXP-0009-mean-reversion-pullback-em-tendencia]], `.claude/state/exp-drafts/EXP-0014-mean-reversion-teto-025.md`,
`.claude/state/exp-drafts/EXP-0015-mean-reversion-teto-020.md`, [[EXP-0018-stop-largo]],
[[EXP-0019-piso-atr]] e `.claude/state/notes-T3.47b.md`. O exportador
(`infra/scripts/export_strategies_to_obsidian.py`) não alcança o Postgres da VPS a partir deste host
nesta sessão (`ConnectionRefusedError`) — rodá-lo confirma os campos e substitui esta nota quando o
banco estiver acessível. `EXP-0014` e `EXP-0015` (as versões `v2`/`v3`) continuam como rascunhos em
`.claude/state/exp-drafts/`, não arquivados no vault; os números acima vêm deles diretamente.

**Linhas `v9`/`v10` acrescentadas à mão pela Sexta-feira em 2026-09-09** a partir de
`.claude/state/notes-T3.54.md` e [[EXP-0021-timeframe]]. `v9` e `v10` não têm página individual nesta
sessão pelo mesmo motivo acima (exportador sem acesso ao Postgres da VPS). `v10` é, nesta data, a
**única** coorte de `mean_reversion` com população julgável (`n ≥ 30`) e veredito `robusto` — mas o
ganho é de amostra (o piso de ATR% quase não morde em 1 h), não de expectativa: a expectativa bruta e
líquida por decisão não se distingue da `v6` (IC do contraste transversal cobre zero).

**Linha `v11` acrescentada à mão pela Sexta-feira em 2026-09-09** a partir de
`.claude/state/notes-T3.52d.md` (T3.52d) e [[EXP-0020-regime-gate]]. Portão de elegibilidade por
regime (`eligibility_policy`, `docs/PIPELINE.md` §4b item 10) — mede exatamente o que o pai
decidiria dentro do rótulo permitido, sem mudar parâmetro nenhum. Achado de método da mesma
corrida, registrado em `docs/PIPELINE.md` §4b itens 11–12 e `docs/plans/SHADOW-LAB.md`: uma versão
com portão **não** é subconjunto do pai nas decisões (só nas barras), e o critério K4
(`unavailable`) deixa de ser mensurável nela — o número honesto é o K4 do pai. Sem página própria
nesta sessão.

**Acréscimo de 2026-09-10 (plantão de arquivamento, T3.62b) — as linhas `v1`/`v2`/`v10` corrigidas
para o veredito de 90 dias.** As avaliações de 31/17/7 dias citadas acima nas linhas antigas da
tabela **não foram apagadas do histórico** (continuam nas páginas de EXP de origem); a coluna
"Veredito" da tabela `<!-- generated:start -->` foi **atualizada** para refletir a leitura mais
recente e maior, como o gerador faria — ver [[EXP-0025-mean-reversion-90-dias]] para a nota completa,
datada e append-only. Resumo: `mean_reversion` replayada em **90 dias × 16 mercados** (36 corridas,
414 720 barras, 1 644 decisões, 0 erros) mostra as três versões **negativas** no eixo `r_ex_funding`
(cobertura 100 %, forçado pela ausência de `funding_rates` antes de 2026-08-08T16:00Z): `v10`
−0,0293 R/PF 0,910, `v1` −0,0910 R/PF 0,851, `v2` −0,0343 R/PF 0,940 — **K3 dispara nas três**, pela
primeira vez com população suficiente para a régua julgar (≥ 100 avaliáveis e ≥ 30 dias). O motivo:
nas três, as janelas de junho–julho e julho–agosto são negativas e só agosto–setembro é positiva, com
o Δ(J3 − J1J2) excluindo zero nas três (`v10` +0,2265 R, IC [+0,0085; +0,4293]) — **a vantagem medida
antes era a janela de agosto, e só ela**. Os 4 mercados originais que geraram a hipótese caem para
+0,0002 R (exatamente zero) em 90 dias. C5 (fração acima do teto de risco de 3 % do `paper_v1`) é
16,8 % nos 90 dias inteiros contra 32,3 % só na janela de agosto — **propriedade de versão × regime**,
não só de versão. **Nenhuma das três é candidata a linha `paper` neste desenho**; nenhuma foi
depreciada por esta tarefa (recomendação para o orquestrador). O que sobra de valioso é a hipótese de
um portão de regime que restrinja a família à janela em que ela funciona — versão nova, não ajuste,
no mesmo desenho do [[EXP-0020-regime-gate]].


**Acréscimo de 2026-09-10 (T3.76, quant-engineer) — o portão de regime foi medido em 90 dias, e não
salva a família.** O parágrafo acima terminava dizendo que "o que sobra de valioso é a hipótese de um
portão de regime que restrinja a família à janela em que ela funciona". Ela foi testada hoje, com
pré-registro em [[EXP-0026-regime-como-estrategia]] escrito **antes** das corridas. Três braços
derivados da `v10` (conjunto congelado byte a byte, só `eligibility_policy` muda) e replayados nos
mesmos 90 dias × 16 mercados, 12 fatias cada, 138 240 barras cada, 0 erros:

| braço | portão | n / dias | ex-funding | PF | Δ vs pai | IC 95 % do Δ (blocos de dia) | estresse |
|---|---|---:|---:|---:|---:|---|---|
| `v15` | `SIDEWAYS,LOW_VOLATILITY` | 209 / 35 | **+0,0359** | 1,134 | +0,0651 | [−0,0832; +0,2024] | frágil a custos, dependente de metade |
| `v16` | `SIDEWAYS` | 169 / 30 | **+0,0451** | 1,175 | +0,0744 | [−0,1135; +0,2362] | frágil a custos |
| `v17` | `HIGH_VOLATILITY` (falseamento) | 222 / **21** | **+0,0613** | 1,223 | +0,0905 | [−0,1540; +0,2763] | frágil a custos, dependente de metade |

Pai `v10` na mesma janela: −0,0293 R, PF 0,910, 798 decisões em 89 dias.

Três leituras, e a terceira é a que decide. **(1) O portão funciona exatamente como portão:** o Δ
pareado por (mercado, barra) contra o pai é **0,0000 R** nos três braços (202/209, 159/169 e 216/222
barras compartilhadas), e as 7/10/6 decisões que sobram são a divergência de máquina de estados do
slot que o `docs/PIPELINE.md` §4b item 11 já previa. **(2) O sinal de calendário sobrevive ao corte
por regime:** os três braços passam "positivo em 2 das 3 janelas" e nenhum leave-one-market-out fica
negativo, mas o estresse marca os três como **frágeis a custos** (custo ×2 leva os três a expectativa
negativa) e dois deles como **dependentes de metade**. **(3) O intervalo não exclui zero em nenhum
braço.** O portão compra expectativa **pagando em dias**: a `v17` concentra 222 decisões em 21 dias, e
o bootstrap de blocos de dia tem 21 blocos — o IC nasce com ±0,2 R de largura. É por isso que os três
foram **descartados** pela regra pré-registrada, apesar de todos terem ponto positivo.

**E o braço de falseamento venceu.** `HIGH_VOLATILITY` — pré-registrado como "esperado pior" — tem o
maior ponto (+0,0613 R) e o maior PF (1,223), acima dos dois braços de consolidação. A hipótese
"a vantagem é a consolidação" está **refutada**; o que sobrou é a hipótese oposta, e ela **não** pode
ser declarada vencedora aqui: `HIGH_VOLATILITY` é candidata a disfarce de calendário (176 das suas 337
horas estão em agosto–setembro, e o estresse mostra 1ª metade −0,0960 contra 2ª metade +0,2000).

Recomendação ao orquestrador: aposentar `v15`, `v16` e `v17` (a tarefa não conseguiu — ver
`.claude/state/notes-T3.76.md` §7: o HEAD da VPS foi para um commit sem imagem construída e
`compose.sh ops` recusa por desenho). Enquanto isso as três estão **`active`** e decidindo na faixa
viva.

**Acréscimo de 2026-09-11/12 (T3.89, quant-engineer) — o portão de amplitude do universo
(`breadth_v2`) também não salva a família, e a cláusula de identidade aponta para o mesmo regime.**
[[EXP-0027-amplitude]] testou a hipótese de que a fração do universo caindo nos 5 min antes do
fechamento da barra separa a expectancy da reversão compradora — braço A (`v18`, célula "de dentro",
`breadth 0,10–0,60`) e braço B de falseamento (`v19`, `0,60–1,00`), ambos derivados de `v10` byte a
byte, replayados em 2026-06-14 → 2026-09-10 (88 d, o início da série):

| braço | portão | n / dias | ex-funding | PF | Δ não pareado vs pai | IC 95 % (semente 20260912) | estresse |
|---|---|---:|---:|---:|---:|---|---|
| `v18` (A) | `breadth 0,10–0,60` | 540 / 84 | **−0,0475** | 0,851 | **−0,0184** | [−0,1692; +0,1350] | `sem_vantagem_na_base` |
| `v19` (B, falseamento) | `breadth 0,60–1,00` | 316 / 75 | **+0,0081** | 1,024 | **+0,0372** | [−0,1574; +0,2232] | frágil a custos |

Pai `v10` cortado no mesmo início: −0,0291 R, PF 0,911, 789 decisões em 87 dias.

**A célula "de dentro" saiu pior que o pai** — o oposto do que a hipótese principal precisa para ser
verdadeira — e o **braço de falseamento saiu melhor**, replicando o gradiente monótono já visto na
leitura descritiva pré-replay (T1 baixo > T2 meio > T3 alto). Nenhum dos dois passa: 1 de 3 janelas
de 30 d positiva nos dois, leave-one-market-out negativo nos dois (16 de 16 em A, 1 de 16 em B), e o
Δ de A tem o sinal errado. **A condição 5 (Δ pareado por mercado-barra) confirma o instrumento**:
0,0000 R nos dois braços — o portão só remove barras, não muda a decisão nas que sobram. **A cláusula
de falsificação fecha o caso**: cortar o pai por `regime_hourly_v1` em vez de `breadth_v2` produz
separação **igual ou maior** nos dois braços (+0,0017 ≥ −0,0184 em A; +0,1456 ≥ +0,0372 em B) —
`breadth_v2`, nesta coorte, não é um estado que a família deveria pagar por vigiar além do regime
horário do BTC, já descartado como estratégia pela [[EXP-0026-regime-como-estrategia]]. Ambos
aposentados no mesmo dia: `v18` às 2026-09-12T01:15:24Z, `v19` às 01:16:02Z (22:15/22:16 BRT de
2026-09-11), `successor=none`.

**Acréscimo de 2026-09-12 (T3.91, quant-engineer) — o portão de dispersão BTC × alts não chegou a
ser derivado: a célula pré-registrada quase não existe na história.** [[EXP-0029-dispersao-btc-alts]]
pré-registrou dois braços de `v10` sobre a série nova `dispersion_24h_v1` (mediana do retorno de 24 h
das 16 alts menos o do BTC, por minuto): A = discordância `[−0,10; −0,03)` (`v20`) e B = falseamento
`[0; 0,10)` (`v21`), com uma checagem de população **antes** de derivar (A entre 10 % e 30 % das
barras de 15 min, B entre 20 % e 40 %). O backfill de 88 dias (06-16 → 09-11, 126 720 linhas, 16/16 em
todo minuto) foi lido às 04:40 BRT: **A cobre 1,48 % das 8 352 barras (124 barras em 9 dias, 55 delas
o próprio 10/09, zero em 07-16 → 08-15) e B cobre 44,85 %** — os dois fora da faixa. A série é
estreita (mediana −0,0013, desvio 0,0132, p05 −0,0210): o corte −0,03, tirado das duas leituras que
motivaram H-P18, é percentil ~1,5, não um estado. **Nenhuma versão foi derivada, nenhum replay rodou,
nada foi aposentado** — `v19` continua a última da família. Leitura descritiva no pai (não move a
régua): a pior célula é a queda conjunta `[−0,03; 0)` (342 decisões, −0,0721 R), B é +0,0203 R (414
decisões), tercis não monótonos (+0,1502 / −0,0468 / +0,1016). Se H-P18 voltar, é EXP nova com faixas
calibradas nos quantis da série.
