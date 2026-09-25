---
tags: [knowledge, nota, meme, pumpfun, snipers, R, porta, backtest, m5]
tema: memecoin / pump.fun / o piso de snipers do KB-0101 paga em R, ou só em graduação? (5 dias, saída simulada do KB-0099)
fonte: banco da VPS (meme_features_15s, meme_features_1m, meme_tokens), 12–16/09/2026
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r8-q01-r-por-moeda-com-snipers.sql
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-r8-q0{1,2}-*.sql; 315 apostas em 5 dias)
hipotese_testavel: sim
astra: não consultada nesta nota (medição quant, 16/09)
confiança: backtest do autor
owner: astra
updated: 2026-09-16
status: vivo
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0102 — Snipers pagam em R, ou só em graduação?

A [[11-KNOWLEDGE/KB-0101-snipers-e-graduacao-a-medida-com-n-grande|KB-0101]] mediu **graduação** e fechou com a ressalva
certa: "sniper alto também é quem despeja; antes de virar padrão o piso precisa do R medido". Esta nota mede o **R**.

## 1. Como foi medido (reuso literal do KB-0099)

- **Universo = janela do executor** (KB-0101 §3): a **primeira** foto de 15 s com `age_s` 30–300 s, curva viva,
  não-Mayhem (`mayhem_enabled = false` **e** `mayhem_mode IS NULL`), `curve_progress_pct` 0,02–0,50 (**fração**, §4 do
  KB-0099), fita presente (`tape_reason IS NULL`), `net_sol_flow_60s > 0`, `dev_share <= 0,10` e pedigree do KB-0099
  (`creator_serial <= 1/h`, `symbol_clone <= 2/24 h`). `snipers` é lido **nessa foto** — é o que a mesa vê ao decidir.
- **Entrada = a primeira barra de 1 min** depois dessa foto (até 5 min) que satisfaz a porta calibrada do KB-0099:
  `holders >= 20`, `unique_buyers >= 10`, `sells_1m/buys_1m <= 0,6`. **Sem filtro de snipers** — snipers é a variável em teste.
- **Saída = a metodologia do KB-0099 §3, sem mudar nada**: barras de 1 min, alvo 3×, trailing 35 % armado depois de 1,5×,
  piso −50 %, taxa 1,75 % por perna, stop preenchido no **mcap observado** da barra. `R = (múltiplo líquido − 1) / 0,5`.
- **IC 95 % por bootstrap de blocos de dia** (5 blocos, 10 mil reamostragens).
- SQL: `infra/scripts/sql/research/2026-09-16-r8-q01-r-por-moeda-com-snipers.sql` (R por moeda) e
  `…-r8-q02-preco-de-entrada-e-dump-por-faixa.sql` (preço de entrada, atraso, pico e vale). **315 apostas** em 5 dias
  (12 e 16/09 são parciais — 15 e 14 apostas; 14 e 15/09 dão 95 e 122).

## 2. R por faixa de snipers — e **não** é monótono como a graduação

| Snipers na 1ª foto | n | R médio | R mediano | ≥ +2 R | ≤ −0,5 R | R total | IC 95 % (R médio) |
|---|---|---|---|---|---|---|---|
| 0–2 | 27 | **−0,156** | −0,553 | 11,1 % | **55,6 %** | −4,20 | [−0,58; +0,24] |
| 3–10 | 53 | +0,054 | −0,466 | 15,1 % | 49,1 % | +2,87 | [−0,33; +0,44] |
| 11–20 | 73 | +0,037 | −0,336 | 11,0 % | 46,6 % | +2,67 | [−0,24; +0,22] |
| 21–30 | 52 | +0,116 | −0,243 | 11,5 % | 40,4 % | +6,03 | [−0,03; +0,24] |
| **31–60** | 84 | **+0,522** | −0,022 | **20,2 %** | 39,3 % | **+43,83** | [+0,36; +0,72] |
| > 60 | 26 | +0,046 | −0,196 | 11,5 % | 42,3 % | +1,19 | [−0,21; +0,43] |
| **total** | 315 | +0,166 | −0,306 | 14,3 % | 44,4 % | +52,38 | [+0,06; +0,23] |

Nenhuma moeda caiu na faixa `desconhecido`: a porta exige fita e holders lidos, então `snipers IS NULL` não sobrevive a ela.

**A forma é outra.** A graduação subia monotonamente até a última faixa; o R **não**: sobe de 0–2 (negativo) até 31–60 e
**desaba em > 60** (+0,05, dentro do ruído). O R é uma **corcova com topo em 31–60**, não uma rampa.

**Por que a cauda boa some acima de 60** (q02, medianas por faixa): a moeda com > 60 snipers **entra mais tarde e mais cara**
— 150 s da foto até a barra que passa a porta, contra **54 s** na faixa 31–60, e base de entrada mediana de 72,2 SOL contra
65,3 — e **despeja mais**: 34,6 % das apostas com > 60 visitam ≤ 0,5× (a pior taxa de todas) e só **7,7 %** chegam a 3×,
contra **17,9 %** em 31–60. Em 0–2 o problema é o oposto: pico mediano 1,14× e 55,6 % saindo em ≤ −0,5 R — não há comprador
do outro lado. Sniper é **atenção**, e a atenção paga até o ponto em que o mesmo sniper vira a oferta.

**Honestidade estatística:** a vantagem de 31–60 é **cauda**, não acerto (a mediana continua negativa, −0,02). Das 34 saídas
no alvo 3× das 315 apostas, **15 estão nessa faixa**: 17,9 % contra 8,2 % no resto, **p = 0,003** (binomial unilateral),
≈ 0,02 depois de corrigir pelas seis faixas testadas. O bootstrap de blocos de dia dá [+0,32; +0,73] para a diferença
31–60 × resto, mas com **5 blocos** (dois parciais) esse IC é otimista: ele captura a variação entre dias, não a de quem
levou a cauda.

## 3. As regras: teto 25, piso 11, piso 21, sem restrição

| Regra (mesmo universo) | n (5 d) | apostas/dia (14–15/09) | R médio | R mediano | ≥ +2 R | ≤ −0,5 R | R total | IC 95 % |
|---|---|---|---|---|---|---|---|---|
| sem restrição de snipers | 315 | 108 | +0,166 | −0,306 | 14,3 % | 44,4 % | +52,38 | [+0,06; +0,23] |
| `max_snipers <= 10` (hoje) | 80 | 26 | **−0,017** | −0,508 | 13,8 % | 51,2 % | −1,33 | [−0,26; +0,21] |
| `max_snipers <= 25` (KB-0099) | 185 | 62 | +0,097 | −0,345 | 13,5 % | 45,9 % | +17,97 | [−0,04; +0,20] |
| `min_snipers >= 11` | 235 | 82 | +0,229 | −0,231 | 14,5 % | 42,1 % | +53,71 | [+0,11; +0,31] |
| **`min_snipers >= 21`** | 162 | 58 | **+0,315** | −0,193 | 16,0 % | 40,1 % | +51,04 | [+0,23; +0,41] |
| banda 11–60 | 209 | 72 | +0,251 | −0,241 | 14,8 % | 42,1 % | +52,52 | [+0,12; +0,35] |

**O piso paga em R; o teto custa.** O teto de hoje (≤ 10) é **negativo** (−0,017 R) e ainda joga fora 3/4 das apostas. O teto
25 proposto pelo KB-0099 é positivo, mas **pior do que não filtrar** (+0,097 contra +0,166) e seu IC cruza o zero — ele
sobreviveu no KB-0099 porque lá a comparação era contra o teto 10, não contra "sem teto". O piso ≥ 21 quase **dobra** o R
médio contra não filtrar e entrega praticamente o **mesmo R total** (+19 R/dia contra +22 R/dia) com **metade** das apostas:
quase toda a vantagem do universo está em ≥ 21. Mas a decomposição é honesta: 21–30 dá +0,116 e > 60 dá +0,046 — **o piso
≥ 21 é bom porque contém a faixa 31–60**, não porque "quanto mais sniper, melhor". O que os dados sustentam é uma **banda
alta**, não um piso aberto.

## 4. Limites declarados (os do KB-0099, mais um novo e grande)

- **Novo:** o horizonte é de **30 min nominais**, mas a série de 1 min **não cobre 30 min** — a mediana é de **5 barras**
  depois da entrada e **99 % das apostas têm menos de 30 barras** (o rastreio de 1 min acaba quando a moeda sai do orçamento
  de mints). Na prática **58 % das saídas são "tempo" na última barra que existe**, o que trunca as **duas** caudas e faz
  deste R algo mais próximo de um R de ~5 min. O mesmo vale para o KB-0099 (que declarou 10 min); a comparação entre faixas
  não é afetada, o **nível** de R é.
- Sem impacto/slippage além da taxa e sem teto de participação na saída
  ([[11-KNOWLEDGE/KB-0088-o-teto-de-participacao-nos-motores-de-backtest|KB-0088]]) — e aqui a vantagem é **toda** cauda.
- Sem atraso de decisão ([[11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes|KB-0087]]), sem TTL/dedup/cooldown, e **sem**
  `curve_volume_60s_sol >= 5`: a porta desta nota é a do brief (holders, compradores, razão), não a `operator/5` inteira.
- 5 dias, dois parciais; 315 apostas e **26 a 84 por faixa**. É coorte, não holdout: qualquer braço novo nasce
  **pré-registrado como `descartar`** ([[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]]).

## 5. Recomendação (3 linhas)

1. **O teto 25 sai da proposta do KB-0099**: ele é pior do que não filtrar (+0,097 × +0,166 R, IC cruzando zero), e o teto
   ≤ 10 de hoje é **negativo** — teto de snipers só volta como limite de risco declarado, nunca como filtro de qualidade.
2. **O piso entra, como banda**: para a mesa do estágio 1, `min_snipers >= 21` sem teto (+0,315 R, 58 apostas/dia) é o
   conjunto mais defensável hoje; a leitura crua dos dados é **31–60** (+0,522 R), com o alerta de que ali n = 84.
3. **Braço de pesquisa** (EXP-M5, pré-registrado `descartar`): `flow_v2` com `min_snipers 31 / max_snipers 60`, em papel,
   contra `min_snipers 21` e contra sem-filtro, com R por barra de 1 min e **frequência de 3×** como métrica primária — a
   corcova em 31–60 pode ser tamanho de amostra, e é a única coisa nesta nota que sustenta um piso.

## Ligações

[[11-KNOWLEDGE/KB-0101-snipers-e-graduacao-a-medida-com-n-grande|KB-0101]] ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] ·
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] §6 ·
[[05-EXPERIMENTS/EXP-M5-fluxo-e-holders|EXP-M5]] · `docs/plans/T4-MEME-RADAR.md`
