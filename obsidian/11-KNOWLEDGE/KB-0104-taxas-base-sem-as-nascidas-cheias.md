---
tags: [knowledge, nota, meme, pumpfun, graduacao, base-rate, celula-lenta, m4, m5]
tema: memecoin / pump.fun / as taxas-base da KB-0098 recalculadas sem as "graduações" que nascem cheias
fonte: banco da VPS (meme_tokens, meme_curve_snapshots, meme_features_15s, meme_features_1m), criações de 12–16/09/2026 (dias BRT)
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r12-q02-taxas-base-sem-nascidas-cheias.sql
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-r12-q0{1,2,3,4}-*.sql; 52 146 moedas não-Mayhem em 3 dias cheios, 3 293 graduadas em 5 dias)
hipotese_testavel: sim
astra: não consultada nesta nota (pesquisa quant, 16/09 ~20h BRT)
confiança: 3 dias cheios (13–15/09) + 2 parciais; rótulo por carimbo de observação, não por tempo on-chain
owner: astra-quant
updated: 2026-09-16
status: vivo
---

# KB-0104 — As taxas-base sem as "graduações" que nascem cheias

**Pergunta:** a [[11-KNOWLEDGE/KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo|KB-0103]] mediu que 55,4 % das
graduadas encheram ≤ 60 s do mint (nascem cheias; ninguém as comprou). Quanto disso está dentro das taxas-base da
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] §6, que orientam a mesa e o escopo do
estágio 2 — e o que sobra quando se tira?

## 0. Rótulo e denominador (escritos antes de olhar o resultado)
- **Graduada** = `meme_tokens.completed_at IS NOT NULL` — o mesmo contador que a KB-0098/KB-0101 usam.
- **Nascida cheia** = perna **D** (`completed_at − created_at ≤ 60 s`) **OU** perna **F** (nenhuma linha de 15 s com
  `curve_progress_pct < 0,9` entre `created_at` e `completed_at` — o radar nunca a viu subir). `curve_progress_pct` é
  **fração 0–1** nesta série.
- **Orgânica** = graduada que não cai em nenhuma das duas pernas.
- População: **não-Mayhem** (`coalesce(mayhem_enabled,false) = false`), a mesma convenção da KB-0098 §6.
- Os dois avisos da KB-0103 §5 valem inteiros: `completed_at` é **carimbo de observação**, e em 42,7 % das graduadas ele
  cai ≤ −1 s do `created_at`. "Encheu ≤ 60 s" lê *no máximo o mesmo minuto de observação*, não tempo on-chain.

**Reconciliação com os 55,4 % da KB-0103 (e a primeira surpresa):** em 14–16/09, das 2 892 graduadas, a perna D pega
**1 585 de 2 163 não-Mayhem (73,3 %)** e **15 de 729 Mayhem (2,1 %)** — média ponderada 55,3 %, que é o número da KB-0103.
Ou seja: **as graduações Mayhem quase nunca nascem cheias, e é exatamente a população não-Mayhem — a que a KB-0098 conta —
que está 3/4 forjada.** Os 55,4 % subestimam a contaminação do número que a mesa usa.

## 1. Por dia (12–16/09 BRT), graduadas não-Mayhem
| Dia BRT | Graduadas | Perna D (≤ 60 s) | Perna F (nunca viu subir) | Nascidas cheias (D ou F) | **Orgânicas** | % nascidas cheias | IC 95 % |
|---|---|---|---|---|---|---|---|
| 12/09 (parcial) | 619 | 456 | 591 | 593 | **26** | 95,8 % | 93,9–97,1 |
| 13/09 | 680 | 506 | 561 | 572 | **108** | 84,1 % | 81,2–86,7 |
| 14/09 | 738 | 559 | 604 | 617 | **121** | 83,6 % | 80,8–86,1 |
| 15/09 | 754 | 523 | 524 | 551 | **203** | 73,1 % | 69,8–76,1 |
| 16/09 (parcial) | 502 | 391 | 386 | 406 | **96** | 80,9 % | 77,2–84,1 |

**Só a perna D** (a conservadora, que não depende de cobertura): 73,7 % / 74,4 % / 75,7 % / 69,4 % / 77,9 % nos cinco dias,
IC 95 % de ±3,3 pp cada (Wilson). **A perna D sozinha já é 7 em cada 10 graduações não-Mayhem** — a perna F acrescenta pouco
nos dias recentes (28 moedas em 15/09, 15 em 16/09) e muito nos antigos (137 em 12/09), porque **F mistura "nasceu cheia"
com "falta de cobertura do radar"**: das 754 graduadas de 15/09, 491 nunca tiveram nenhuma linha de 15 s (Q03). Por isso a
nota mostra as duas colunas e usa a perna D como **limite inferior** do efeito.

A queda ao longo dos dias (95,8 % → 73,1 %) acompanha a melhora de cobertura do radar, não necessariamente menos forja:
**não ler essa série como "o viveiro está diminuindo"**.

## 2. As taxas-base da KB-0098 §6 recalculadas (3 dias cheios: 13, 14 e 15/09; 52 146 moedas não-Mayhem com foto)
| Medida | **Original (KB-0098 §6)** | **Sem as nascidas cheias (D ou F)** | Só perna D |
|---|---|---|---|
| Passaram de 10 SOL reais | 8 711 (16,7 %) | **7 400 (14,2 %)** | 7 416 (14,2 %) |
| Passaram de 30 SOL reais | 3 364 (6,45 %) | **2 064 (3,96 %)** | 2 080 (3,99 %) |
| **Encheram a curva / graduaram (≈ 85 SOL reais)** | 1 999 (**3,83 %**) | **432 (0,83 %)** | 448 (0,86 %) |
| Mediana de tempo até 30 SOL | 0,61–0,70 min | **0,86–1,25 min** | 0,83–1,24 min |
| Célula lenta (30 SOL após ≥ 3 min) | 614 (~205/dia) | **613** | 614 |
| Graduação da célula lenta | 121/614 = **19,7 %** | **120/613 = 19,6 %** | 121/614 = 19,7 % |
| **Razão célula lenta / base** | **5,1×** | **23,6×** | 22,9× |

Por dia (graduadas não-Mayhem / orgânicas): 13/09 **609 / 108**, 14/09 **668 / 121**, 15/09 **722 / 203**.
Célula lenta por dia: 13/09 136 (136 orgânicas), 14/09 184 (183), 15/09 294 (294).

**Os três fatos que importam:**
1. **O contador de graduação por dia cai 4,6×**, não 2×: de ~670/dia para **~145/dia** de graduações orgânicas
   (0,83 % das moedas novas, não 3,9 %). O "2×" da KB-0103 §4.3 valia para a população **com** Mayhem.
2. **A célula lenta não se mexe.** 614 → 613 moedas e 19,7 % → 19,6 % de graduação: **nenhuma** das lentas era nascida
   cheia — por construção (quem cruza 30 SOL com ≥ 3 min de vida foi visto subindo) e por medição. A célula lenta é o
   único número da KB-0098 que sai inteiro desta errata.
3. **A vantagem da célula lenta é 4,6× maior do que a KB-0098 anunciou**: não "5× a média", e sim **~23× a média
   orgânica**. O denominador estava inflado; o numerador da lenta estava limpo. É a única conclusão desta nota que
   **aumenta** o valor de uma tese existente (EXP-M7) — e por isso precisa de replicação antes de virar tamanho de aposta.

**O patamar "85 SOL reais" pela foto de curva não serve de medida** (Q02, colunas `ge85_*`): a foto lê
`real_sol_reserves ≥ 85` em ~390/dia, e destas **3 a 4 por dia** são orgânicas. Motivo: a foto de curva (60 req/min para o
universo inteiro) quase só pega `≥ 85` quando a moeda **já estava cheia na primeira foto** — que é a definição de nascida
cheia. Para "encheu", usar `completed_at`, nunca o pico da foto.

## 3. O que muda (e o que não muda) nas decisões já tomadas
| Decisão | Usou graduação total ou orgânica? | Muda? |
|---|---|---|
| **"~7 propostas/hora"** ([[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio\|KB-0099]]: 71 candidatos em 10 h de 15/09 = 7,1/h) | **Nenhuma das duas.** É contagem de **candidatos da porta no replay da série de 15 s**, não taxa de graduação. | **Não muda.** As nascidas cheias nem entram no denominador: 65 % das graduadas de 15/09 não têm uma única linha de 15 s, e a porta só vê o que tem série. O alvo de 5–10/hora e o R de +0,08 a +0,27 ficam de pé. |
| **"0,25 SOL só acima de 53 % da curva"** ([[03-TRADING/Meme/Estudo-2026-09-16-tamanho-estagio-2\|Estudo T4.29b]]) | **Nenhuma das duas.** Os 53,1 % são **aritmética da curva** (impacto = SOL ÷ reserva virtual de SOL, teto 0,5 %, reserva ≤ 115,005 SOL) — não há graduação na conta. | **Não muda o limiar.** O que poderia mudar é a contagem "582 moedas/dia". Recomputado (Q03 bloco b; 15/09, não-Mayhem, idade 0–30 min): dos **4 886 minutos-moeda** com progresso ≥ 53,1 %, só **39 (0,8 %)** são de nascidas cheias, em **38 de 1 068 moedas (3,6 %)**. Efeito **imaterial**; a conclusão "0,25 SOL fica fora da janela 5–50 %" não se move. |
| **KB-0098 §2/§6 "3,9 % graduam"** | total | **Muda muito**: 0,83 % (§2 acima e a errata na própria KB-0098). |
| **KB-0101 (snipers e graduação)** | total | **A recalcular** — não medido aqui. Se o desfecho "graduou" inclui nascidas cheias e os snipers são quem as enche, a associação pode ser quase toda artefato. **Marcado, não resolvido.** |

## 4. Conclusão (4 linhas)
1. Na população que a mesa conta (não-Mayhem), **73–78 % das "graduações" nascem cheias** — bem acima dos 55,4 % da
   KB-0103, porque as Mayhem (2,1 % de perna D) diluíam a média.
2. A taxa-base de graduação cai de **3,83 % para 0,83 %** (~670 → ~145 moedas/dia); 10 e 30 SOL reais caem pouco
   (16,7 → 14,2 % e 6,45 → 3,96 %) e a mediana de tempo até 30 SOL passa de ~0,65 para ~1,0 min.
3. **A célula lenta sai intacta** (614 → 613 moedas, 19,7 → 19,6 %) e por isso sua vantagem sobre a base passa de
   **5× para ~23×** — é o único número da KB-0098 em que dá para se apoiar hoje, e o argumento mais forte da EXP-M7.
4. As duas decisões vivas (cadência da KB-0099, tamanho da T4.29b) **não dependiam da graduação** e ficam de pé; o que
   precisa ser refeito é todo placar que usa "graduou" como desfecho — **KB-0101 em primeiro lugar**.

## 5. O que fica em aberto (não mascarar)
- **3 dias cheios**, dois parciais. Sem replicação, é anedota com n grande (mesmo aviso de KB-0100/KB-0103).
- A perna F **confunde forja com falta de cobertura**; por isso a coluna "só perna D" existe e as conclusões são lidas por
  ela. As duas concordam dentro de 0,03 pp na taxa-base de graduação.
- `completed_at` é carimbo de observação (KB-0103 §5). Uma medida limpa exigiria o slot on-chain do `complete`.
- **Não foi medido:** o efeito sobre a KB-0101 (snipers), sobre o placar de apostas e sobre qualquer marca que use
  "graduou" como rótulo positivo.

## Ligações
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] (errata de 16/09) ·
[[11-KNOWLEDGE/KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo|KB-0103]] ·
[[11-KNOWLEDGE/KB-0101-snipers-e-graduacao-a-medida-com-n-grande|KB-0101]] ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] ·
[[05-EXPERIMENTS/EXP-M7-organica-lenta]] · [[03-TRADING/Meme/Estudo-2026-09-16-tamanho-estagio-2|Estudo T4.29b]]
