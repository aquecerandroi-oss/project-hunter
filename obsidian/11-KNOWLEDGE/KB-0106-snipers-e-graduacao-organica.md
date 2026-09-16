---
tags: [knowledge, nota, meme, pumpfun, snipers, graduacao, organica, portao, base-rate, m5]
tema: memecoin / pump.fun / o KB-0101 refeito com o desfecho limpo — snipers na 1.ª foto x graduação ORGÂNICA
fonte: banco da VPS (meme_features_15s, meme_tokens, meme_curve_snapshots), 12–16/09/2026
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r15-q01-snipers-x-graduacao-organica.sql
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-r15-q0{1,2}-*.sql; 64 879 moedas não-Mayhem, 5 dias, 551 graduações orgânicas)
hipotese_testavel: sim
astra: não consultada nesta nota (pesquisa quant, 16/09 ~22h BRT)
confianca: backtest do autor; 3 dias cheios + 2 parciais
owner: astra-quant
updated: 2026-09-16
status: vivo
---

# KB-0106 — Snipers e graduação orgânica (refazendo o KB-0101 sem as nascidas cheias)

**Pendência que esta nota fecha:** a [[11-KNOWLEDGE/KB-0104-taxas-base-sem-as-nascidas-cheias|KB-0104]] §3 marcou o
[[11-KNOWLEDGE/KB-0101-snipers-e-graduacao-a-medida-com-n-grande|KB-0101]] como **"a recalcular"**: se 3/4 das
"graduações" não-Mayhem **nascem cheias** (`completed_at − created_at ≤ 60 s`, ninguém as comprou) e sniper alto é
justamente quem as enche, a escada do KB-0101 podia ser **quase toda artefato**. Medido: **não é.**

## 0. O que mudou e o que não mudou na medição (escrito antes de olhar o resultado)
- **Universo, unidade e janela: idênticos ao KB-0101** (reuso literal do `r7-q01`). Uma linha = uma moeda; `snipers` lido
  na **primeira foto de 15 s com `age_s` 30–120 s**; Mayhem fora (`mayhem_enabled = true` **ou** `mayhem_mode` não nulo);
  janela do executor = a mesma foto com `curve_progress_pct` 0,02–0,50 (fração 0–1), `tape_reason IS NULL`,
  `net_sol_flow_60s > 0`.
- **Só o desfecho mudou.** Antes: `completed_at IS NOT NULL OR migrated_at IS NOT NULL`. Agora, três colunas lado a lado:
  - `graduou` = `completed_at IS NOT NULL` (desfecho limpo do KB-0104; `migrated_at` **não acrescenta uma única moeda** em
    nenhuma faixa — os dois contadores dão exatamente o mesmo número);
  - `organica` = `graduou` **E** `completed_at − created_at > 60 s` **E** existe ao menos **uma foto de 15 s com
    `curve_progress_pct < 0,9` entre `created_at` e `completed_at`** — a negação literal da definição de "nascida cheia"
    do `r12-q02` (pernas D e F);
  - `só perna D` = `graduou` e `> 60 s`, sem exigir a foto — o **limite inferior**, que não depende de cobertura do radar.
- **Cobertura:** 12–16/09 BRT, um dia por consulta. **64 879 moedas** (o KB-0101 contou 64 267; a diferença de +612 é o
  dia 16/09 medido ~6 h mais tarde — mesma coorte, mais moedas no dia parcial).
- SQL: `infra/scripts/sql/research/2026-09-16-r15-q01-snipers-x-graduacao-organica.sql` (faixas finas, um dia por
  execução) e `…-r15-q02-tetos-e-pisos-organica.sql` (tetos/pisos direto no banco, usado como conferência).

## 1. Universo inteiro (todas as não-Mayhem com foto aos 30–120 s), 5 dias

| Snipers na 1ª foto | Moedas | ≥ 30 SOL reais | Graduou (contador KB-0101) | **Graduou ORGÂNICA** | IC 95 % (orgânica) | Nascidas cheias entre as graduadas | Pico mediano `mcap_sol` |
|---|---|---|---|---|---|---|---|
| 0–2 | 40 819 | 203 (0,50 %) | 55 (0,13 %) | **48 (0,118 %)** | [0,09; 0,16] | 12,7 % | 28 |
| 3–10 | 12 276 | 462 (3,76 %) | 109 (0,89 %) | **91 (0,741 %)** | [0,60; 0,91] | 16,5 % | 33 |
| 11–30 | 7 042 | 814 (11,6 %) | 211 (3,00 %) | **186 (2,641 %)** | [2,29; 3,04] | 11,8 % | 41–63 |
| 31–60 | 3 400 | 736 (21,7 %) | 158 (4,65 %) | **141 (4,147 %)** | [3,53; 4,87] | 10,8 % | 60–74 |
| > 60 | 1 342 | 607 (45,2 %) | 105 (7,82 %) | **85 (6,334 %)** | [5,15; 7,77] | 19,0 % | 88–111 |
| desconhecido | 650 | 14 (2,15 %) | 68 (10,5 %) | **3 (0,462 %)** | [0,16; 1,35] | **95,6 %** | 29 |
| **total (sem desconhecido)** | 64 879 | 2 822 (4,35 %) | 638 (0,98 %) | **551 (0,849 %)** | [0,78; 0,92] | 13,6 % | — |

Pelo limite inferior (só perna D) seriam **586 (0,903 %)** em vez de 551 — as duas leituras concordam dentro de 0,05 pp,
como no KB-0104.

**A escada continua monotônica, e nos cinco dias separados** (0,118 → 0,741 → 2,641 → 4,147 → 6,334 %; nenhuma inversão de
faixa em nenhum dos 5 dias). O que mudou de verdade:

1. **A contaminação por nascidas cheias é ~plana entre as faixas de sniper (10,8 % a 19,0 %)** — ela **não** se concentra
   no sniper alto. A hipótese de artefato da KB-0104 §3 está **rejeitada**: tirar as forjadas derruba o nível de todas as
   faixas junto e **preserva a forma**.
2. **A coorte do KB-0101 já era 86 % limpa.** As 638 graduações desta coorte são só ~19 % das ~3 293 graduações
   não-Mayhem de 12–16/09 — porque exigir **uma foto de 15 s aos 30–120 s de vida** já exclui quase toda nascida cheia
   (KB-0104: 65 % das graduadas de 15/09 não têm nenhuma linha de 15 s). Por isso 73–78 % de forja no universo do
   KB-0098 viram **13,6 %** aqui.
3. **A faixa `desconhecido` era 96 % forja.** O KB-0101 chamou de "buraco de medida"; agora está quantificado:
   **65 das 68 "graduações"** dessa faixa nasceram cheias, e a taxa cai de 10,5 % para **0,46 %** — abaixo da faixa 3–10.
   Isso confirma a leitura antiga e fecha a única anomalia da tabela.

## 2. Janela do executor (progresso 0,02–0,50, fita, fluxo > 0) — **quase nada muda**

| Snipers na 1ª foto | Moedas | ≥ 30 SOL reais | Graduou (KB-0101) | **Graduou ORGÂNICA** | IC 95 % | Pico mediano `mcap_sol` |
|---|---|---|---|---|---|---|
| 0–2 | 4 973 | 59 (1,19 %) | 14 (0,28 %) | **14 (0,282 %)** | [0,17; 0,47] | 31 |
| 3–10 | 3 667 | 117 (3,19 %) | 32 (0,87 %) | **32 (0,873 %)** | [0,62; 1,23] | 34–36 |
| 11–30 | 2 164 | 172 (7,95 %) | 49 (2,26 %) | **48 (2,218 %)** | [1,68; 2,93] | 43–57 |
| 31–60 | 1 051 | 147 (14,0 %) | 27 (2,57 %) | **27 (2,569 %)** | [1,77; 3,71] | 58–69 |
| > 60 | 320 | 74 (23,1 %) | 9 (2,81 %) | **9 (2,812 %)** | [1,49; 5,26] | 70–90 |
| **total** | 12 175 | 569 (4,67 %) | 131 (1,08 %) | **130 (1,068 %)** | [0,90; 1,27] | — |

**Das 131 graduações que a mesa via na janela do executor, exatamente UMA era nascida cheia.** E não é sorte: a janela
exige `curve_progress_pct` **entre 0,02 e 0,50 na primeira foto**, e uma moeda que nasce cheia já está em ~1,0 nessa foto.
**A janela do executor é imune à forja por construção** — é o achado mais útil desta nota, e vale para qualquer placar
futuro medido dentro dela.

**Mas a escada, aqui, não é escada: é platô acima de 11.** 2,218 % / 2,569 % / 2,812 % nas três faixas altas, com ICs
completamente sobrepostos (n = 2 164 / 1 051 / 320). O KB-0101 escreveu "a taxa cresce monotonamente até a última faixa
(> 60 = 2,85 %, ainda subindo)" — **isso não se sustenta**: por dia, a janela do executor tem **inversão de faixa em 4
dos 5 dias** (só 14/09 sai monotônico), o que o KB-0101 não checou no escopo `janela_exec` (só no universo). A conclusão
"acima de 60 continua subindo" deve ser lida como **empate**, não como tendência.

## 3. O teto: 10 e 25, dentro × fora (desfecho orgânico)

| Escopo | Teto | Dentro (n / orgânicas) | Fora (n / orgânicas) | **RR fora/dentro** | RR no KB-0101 | Mantém | **Perde das orgânicas** |
|---|---|---|---|---|---|---|---|
| universo | ≤ 10 | 53 095 / 139 (0,262 %) | 11 784 / 412 (3,496 %) | **13,35** [11,03; 16,17] | 13,02 [10,92; 15,54] | 81,8 % | **74,8 %** |
| universo | ≤ 25 | 59 039 / 280 (0,474 %) | 5 840 / 271 (4,640 %) | **9,78** [8,30; 11,54] | 9,61 [8,25; 11,20] | 91,0 % | **49,2 %** |
| janela exec | ≤ 10 | 8 640 / 46 (0,532 %) | 3 535 / 84 (2,376 %) | **4,46** [3,12; 6,38] | 4,52 [3,16; 6,45] | 71,0 % | **64,6 %** |
| janela exec | ≤ 25 | 10 475 / 85 (0,811 %) | 1 700 / 45 (2,647 %) | **3,26** [2,28; 4,66] | 3,33 [2,34; 4,76] | 86,0 % | **34,6 %** |

(RR por Katz, log-RR.) **O teto continua perdendo vencedoras, e por praticamente a mesma margem.** Os ICs do desfecho
orgânico e do desfecho sujo se sobrepõem quase inteiramente — a limpeza **não move o veredito do teto em nenhuma casa
decimal que importe**. O teto **25 de hoje** (mesa) é menos brutal que o ≤ 10, mas ainda joga fora **1 em cada 3**
graduadas orgânicas da janela para economizar 14 % das propostas, e leva a densidade de 1,068 % para **0,811 %** — ou
seja, **o filtro de hoje piora a qualidade média da proposta em 24 %.**

## 4. O piso (a pergunta 11/21 do KB-0101), janela do executor, 5 dias

| Regra | Moedas/5 d | Moedas/dia | Orgânicas | **Por moeda proposta** | IC 95 % | KB-0101 (desfecho sujo) |
|---|---|---|---|---|---|---|
| sem filtro de snipers | 12 175 | 2 435 | 130 | 1,068 % | [0,90; 1,27] | 1,076 % |
| `max_snipers <= 10` (executor) | 8 640 | 1 728 | 46 | **0,532 %** | [0,40; 0,71] | 0,532 % |
| `max_snipers <= 25` (mesa hoje) | 10 475 | 2 095 | 85 | **0,811 %** | [0,66; 1,00] | 0,811 % |
| `min_snipers >= 11` | 3 535 | 707 | 84 | 2,376 % | [1,92; 2,93] | 2,405 % |
| `min_snipers >= 16` | 2 673 | 535 | 70 | 2,619 % | [2,08; 3,30] | 2,656 % |
| **`min_snipers >= 21`** | 2 112 | 422 | 60 | **2,841 %** | [2,21; 3,64] | 2,888 % |
| `min_snipers >= 26` | 1 700 | 340 | 45 | 2,647 % | [1,98; 3,52] | 2,706 % |
| `min_snipers >= 31` | 1 371 | 274 | 36 | 2,626 % | [1,90; 3,61] | 2,626 % |
| banda 11–60 | 3 215 | 643 | 75 | 2,333 % | [1,87; 2,91] | 2,364 % |
| **banda 21–60** | 1 792 | 358 | 51 | **2,846 %** | [2,17; 3,72] | 2,902 % |
| banda 31–60 | 1 051 | 210 | 27 | 2,569 % | [1,77; 3,71] | 2,569 % |

**O piso 21 continua nominalmente ótimo (2,841 %) — e continua indistinguível de 11, 16, 26 e 31.** Todos os cinco pisos
caem em [1,9 ; 3,6] e os ICs se cobrem. O que os dados separam com folga é **piso × teto** (2,8 % contra 0,53–0,81 %),
não **qual** piso. A leitura honesta do KB-0101 ("acima de 21 o ganho é ruído") vira, com o desfecho limpo, **"acima de
11 tudo é ruído"** — e a escolha entre 11 e 21 tem de vir de **outro** critério que não graduação.

## 5. Confronto com o KB-0102 (R por faixa) — as duas medidas agora **convergem**

O [[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] mediu **R** no mesmo universo e achou uma
**corcova com topo em 31–60** (+0,522 R) e desabamento em > 60 (+0,046 R) — e usou como contraste o fato de que o KB-0101
mostrava graduação **subindo** até > 60. Esse contraste **caiu**:

| Faixa | Graduação orgânica na janela (KB-0106) | R médio (KB-0102) |
|---|---|---|
| 0–2 | 0,282 % | −0,156 |
| 3–10 | 0,873 % | +0,054 |
| 11–30 | 2,218 % | +0,037 / +0,116 (11–20 / 21–30) |
| **31–60** | 2,569 % | **+0,522** |
| > 60 | 2,812 % (IC [1,49; 5,26], n = 320) | +0,046 |

Na janela do executor a graduação **não distingue** 11–30, 31–60 e > 60 — logo ela **não contradiz** a corcova do R. As
duas séries dizem a mesma coisa até 30 (sobe forte) e, acima disso, uma cala (graduação, IC largo) e a outra fala
(R: 31–60 paga, > 60 não). **Quando uma medida fica muda e a outra tem sinal, manda a que tem sinal** — e a que tem sinal
é o R, que é a moeda em que a mesa é paga. O mecanismo do KB-0102 §2 (a moeda com > 60 snipers entra 150 s depois e
72,2 SOL mais cara, e 34,6 % visitam ≤ 0,5×) explica exatamente como uma faixa pode **graduar mais** e **pagar menos**:
graduar é o evento; o R é o preço de entrada nele.

## 6. Conclusão (4 linhas)
1. **O KB-0101 sobrevive.** Tirando as nascidas cheias, a escada do universo continua monotônica nos 5 dias
   (0,12 → 0,74 → 2,64 → 4,15 → 6,33 %) e a contaminação é **plana entre faixas** (10,8–19,0 %): a associação
   snipers × graduação **não era artefato de forja**.
2. **Na janela do executor a limpeza é quase um no-op** (131 → 130 graduadas): exigir progresso 0,02–0,50 na 1.ª foto
   **exclui a nascida cheia por construção** — a janela é imune à forja, e isso vale para todo placar medido nela.
3. **O teto continua invertido:** ≤ 10 perde 64,6 % das orgânicas da janela (RR 4,46) e o **teto 25 de hoje perde 34,6 %**,
   baixando a densidade por proposta de 1,068 % para 0,811 %. **O piso 21 continua no topo (2,841 %) e continua empatado**
   com 11/16/26/31 — a novidade é que agora **nem 11 se separa** dos demais.
4. **A única correção real ao KB-0101** é a frase "> 60 ainda subindo": na janela é **platô com inversão em 4 dos 5 dias**,
   e é ali que a corcova de R do KB-0102 passa a mandar sozinha.

## 7. Recomendação
**Para a mesa (teto 25 hoje):** **tirar o teto 25** — ele custa 1 em cada 3 graduadas orgânicas e 24 % da densidade por
proposta, e o KB-0102 já mostrou que ele rende menos R do que não filtrar (+0,097 × +0,166). Trocar por **`min_snipers >= 21`
sem teto** (422 propostas/dia na janela, 2,84 % de graduação orgânica, +0,315 R no KB-0102) — as **duas** medidas
independentes apontam para o mesmo conjunto, que é a razão mais forte para mover a mesa. Teto de snipers só volta como
**limite de risco declarado**, nunca como filtro de qualidade.

**Para o braço de pesquisa (EXP-M5, pré-registrado `descartar`):** manter `flow_v2` com **banda 31–60** contra
`min_snipers 21` e contra sem-filtro, com **frequência de 3× como métrica primária** — graduação **não** serve mais de
desempate acima de 11 (ICs sobrepostos) e o único sinal que resta acima de 30 é o R. Acrescentar duas coisas: (a) medir o
R **também** com o rótulo orgânico no desfecho, para saber se as apostas vencedoras do KB-0102 eram orgânicas; (b) usar
`is_organica` como rótulo padrão em todo placar novo — fora da janela do executor ele muda o número por 4,6× (KB-0104).

## 8. O que fica em aberto
- 3 dias cheios, 2 parciais; 130 graduadas orgânicas na janela do executor, **9 a 48 por faixa**. Coorte, não holdout.
- `completed_at` é **carimbo de observação** (KB-0103 §5), não slot on-chain; a perna D herda esse limite inteiro.
- A perna F ainda confunde forja com falta de cobertura; por isso a coluna "só perna D" existe (586 × 551 no universo).
- **Não medido aqui:** R com desfecho orgânico (recomendação 7b), e o efeito do rótulo orgânico sobre o placar de apostas
  do KB-0099/KB-0102.

## Ligações
[[11-KNOWLEDGE/KB-0101-snipers-e-graduacao-a-medida-com-n-grande|KB-0101]] (esta nota o substitui como placar de graduação) ·
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] ·
[[11-KNOWLEDGE/KB-0104-taxas-base-sem-as-nascidas-cheias|KB-0104]] (pendência §3 fechada) ·
[[11-KNOWLEDGE/KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo|KB-0103]] ·
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] (errata 16/09) ·
[[05-EXPERIMENTS/EXP-M5-fluxo-e-holders|EXP-M5]] · `infra/scripts/sql/research/2026-09-16-r15-q0{1,2}-*.sql`
