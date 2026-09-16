---
tags: [experimento, meme, pumpfun, paper, pre-registro, celula-lenta, progresso, migracao, m5]
updated: 2026-09-16
status: pre-registrado
owner: astra-quant
exp: EXP-M12
strategy: "meme/pumpfun — célula lenta L2′: primeira barra de 1 min com 30 SOL reais na curva, idade ≥ 180 s, holders ≥ 20, fita, fluxo > 0, não-Mayhem, não nascida cheia, com teto de progresso próprio de 0,90"
version: "gate celula_lenta v1 (L2′, curve_progress_max_pct 0,90 por conjunto) + exit alvo_3x_trailing_35_apos_1_5x_tempo_30m_segura_migracao v1 (exit_on_migration = false, marca pela fita da pool)"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-M12 — a célula lenta como porta (L2′), com teto de progresso próprio

> **Pré-registro escrito em 2026-09-16 (noite BRT), ANTES de existir qualquer proposta do conjunto** e antes de
> o motor de risco aceitar um teto de progresso por conjunto. Protocolo congelado; avaliações acrescentadas pelo
> fechamento diário, nunca reescritas. Previsão padrão `descartar`. Disciplina:
> [[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]] ·
> [[06-DECISIONS/2026-09-10-validacao-em-um-dia-e-lucro-real|decisão de 10/09]].

## Diretiva de origem

A [[11-KNOWLEDGE/KB-0104-taxas-base-sem-as-nascidas-cheias|KB-0104]] mostrou que a **célula lenta** — a moeda que
chega a **30 SOL reais** na curva **≥ 3 min** depois da criação — é o único número da
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] que sobreviveu à errata das
nascidas cheias: ~613 moedas/dia e **19,6 % de graduação orgânica (23,6× a taxa-base)**. A
[[11-KNOWLEDGE/KB-0107-celula-lenta-como-porta-da-mesa|KB-0107]] transformou isso em porta e mediu cadência e R em
5 dias. O achado que define esta página: **30 SOL reais não é "5–50 % de curva"** — `curve_progress_pct` é fração
de **tokens vendidos** e 30 SOL levantados correspondem a progresso mediano **0,71** (p10 0,63; p90 0,83). O teto
`curve_progress_max_pct = 0,50` do `MEME_PAPER_V0` **recusa 97 % da célula lenta** por `progress_above_window`
antes de qualquer outro critério. Por isso o braço é **L2′** (linha sem o teto de 0,50), com teto **próprio**.

## Hipótese (congelada)

**H1:** comprar **tarde e devagar** — na primeira barra de 1 min em que a moeda já levantou **30 SOL reais** com
**≥ 180 s** de vida, holders ≥ 20, fita e fluxo positivo — rende expectância positiva **no corpo**, não só na
cauda: a mediana medida é **+0,046 R** (L2′) contra **−0,31 a −0,35** da porta calibrada, e metade do R total vem
de apostas que não são alvo 3×. **H0 (previsão):** o R de +0,349 é uma marcação de **~5 min** (mediana de 4–5
barras no horizonte de 30 min), sem pedigree, sem TTL/dedup/cooldown, sem atraso de decisão e com **~20 % das
entradas graduando dentro do horizonte** — prospectivamente o R médio cai para a faixa de zero → `descartar`.

## Definição congelada (`celula_lenta v1`, variante **L2′**)

Entrada = a **primeira barra de 1 min** em que valem, cumulativamente (busca até **30 min** depois do cruzamento
dos 30 SOL; passado isso, recusa `slow_cell_window_expired`):

| critério | limiar | recusa |
|---|---|---|
| SOL real na curva | `real_sol_reserves ≥ 30` (foto de `meme_curve_snapshots`) | `real_sol_below_min` |
| idade | ≥ 180 s | `age_below_min` |
| **progresso da curva** | **≤ 0,90** — teto **próprio do conjunto**, não o 0,50 do perfil | `progress_above_window` |
| fita | presente (`tape_reason IS NULL`) | `tape_blind` |
| fluxo | `net_sol_flow_1m > 0` | `flow_not_positive` |
| holders | ≥ 20 | `holders_below_min` |
| Mayhem | `mayhem_enabled = false` **e** `mayhem_mode IS NULL` | `mayhem_curve` / `mayhem_unknown` |
| nascida cheia | `completed_at − created_at > 60 s` (KB-0104, perna D) | `born_full` |
| curva | viva (não migrada no instante da entrada) | `curve_completed` |
| participação | ≤ 1 % do volume do minuto | `participation_above_cap` |

Saídas **iguais às da mesa** — alvo **3×**, trailing **35 %** armado depois de 1,5×, piso **−50 %**, tempo
**30 min**, `creator_dump` — **mais `exit_on_migration = false`**: a posição atravessa a conclusão e a migração e
passa a ser marcada pela **fita da pool** (`mark_source = 'pool_tape'`, T4.11 /
[[05-EXPERIMENTS/EXP-M4-moonshot|EXP-M4]]). Tamanho **0,05 SOL** (0,25 SOL **não** cabe no teto de participação);
taxa 1,75 % por perna; `R = (múltiplo líquido − 1) / 0,5`. Sem piso de snipers — L3′ (snipers 21–60, +0,45 R a
1,2 propostas/hora) é **braço irmão futuro**, não este.

## Pré-condição de engenharia (decisão do dono)

O teto de progresso hoje é `curve_progress_max_pct = Decimal("0.50")` **no perfil** `MEME_PAPER_V0`
(`packages/risk-core/hunter_risk_meme/limits.py`), não no conjunto. **Este braço exige `curve_progress_max_pct`
por conjunto no motor de risco** — mexer no motor de risco é decisão do Everton, não da mesa. **Até essa decisão
existir, a página fica pré-registrada e o braço não roda; se rodar, é papel, e só papel.** O teto do executor
(idade ≤ 600 s) **não** precisa mudar: ele custa 39 % das entradas e o que ele corta rende **metade**
(+0,220 × +0,465 em L1′).

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **PASS** | 30 SOL reais levantados devagar são demanda comprovada, não empurrão de bot; 19,6 % de graduação orgânica contra 0,83 % da taxa-base |
| C2 | Sobreajuste | **REVISE** | Quatro variantes (L1′–L4′) foram medidas na mesma amostra e escolheu-se uma; o 0,90 do teto é escolha de engenharia (acima do p90 = 0,83), não varredura |
| C3 | Amostra | **PASS** | 550 entradas em 5 dias (110/dia bruto; **3,2/hora admissíveis** em 13–22 BRT): a régua de 100 apostas fecha com folga |
| C4 | Regime | **REVISE** | O dia manda: 11,7 disparos/h em 15/09 contra 2,5/h em 16/09; 3 dias cheios e 2 parciais |
| C5 | Saídas | **REVISE** | Iguais às da mesa, mas **~20 % das entradas graduam dentro do horizonte** e o R delas depende da marca de pool (T4.11), hoje sem cobertura medida nesta coorte |
| C6 | Concentração | **PASS** | 0,05 SOL e ≤ 1 % do volume do minuto; comprar a ~70 % de curva com 0,05 SOL cabe, com 0,25 SOL não caberia |
| C7 | Execução | **REVISE** | `at_30` é **quando o radar viu** 30 SOL (60 req/min para o universo inteiro), não o slot on-chain; atraso mediano da entrada 37 s, p90 417 s; sem atraso de decisão modelado |
| C8 | Invalidação | **PASS** | Gatilhos abaixo + régua (≥ 100 apostas medidas e 30 dias, IC 95 % por blocos de dia, leave-top-out) + a pré-condição do motor de risco |

## Previsões (congeladas, numéricas)

- **P1** Cadência **admissível** (idade ≤ 600 s) entre **2 e 5 propostas/hora** em 13–22 BRT (in-sample **3,2**);
  ≥ 100 propostas em ≤ 10 dias.
- **P2** R médio prospectivo entre **−0,10 e +0,25**, ponto **+0,05** → `descartar` (H0), contra os **+0,349**
  in-sample (IC de blocos [+0,26; +0,41]). Só R médio ≥ +0,20 **com** leave-top-out ≥ 0 muda a previsão.
- **P3** R **mediano ≥ 0** (in-sample +0,046): é este o teste do mecanismo "a lenta ganha no corpo". Mediana
  negativa = mecanismo falso, e o braço morre mesmo que a média agrade.
- **P4** Progresso mediano na barra de entrada entre **0,65 e 0,80** (in-sample 0,71) e **≥ 90 %** das entradas
  acima de 0,50 — isto é, o braço é **inteiramente** o que o teto do perfil recusa hoje.
- **P5** **≥ 15 %** das apostas graduarão dentro do horizonte (in-sample ~20 %: 21/108, 26/139, 32/205) e
  precisarão de marca de pool; se **> 30 %** delas ficarem sem nenhum trade de pool em 15 min, o instrumento está
  cego (K1) e a leitura é de instrumento, não de braço.

## Gatilhos de descarte (qualquer um basta)

1. R médio ≤ 0 com IC 95 % de blocos de dia contendo o zero depois de **100 apostas medidas e 30 dias**.
2. R mediano < 0 (o mecanismo desta página é o corpo, não a cauda).
3. Leave-top-out negativo — vira o mesmo bilhete de loteria da porta L com teto de 0,50 (28 apostas em 5 dias,
   7 alvos 3× carregando tudo).
4. Cadência admissível < 1/hora em 13–22 BRT por 5 dias seguidos.

## O que NÃO fazer

Subir `curve_progress_max_pct` do perfil `MEME_PAPER_V0` para "fazer o braço caber" — o teto tem de nascer **por
conjunto**, e a mudança é decisão do dono; subir o teto de idade do executor (não é ele que bloqueia: custa 39 %
das entradas que rendem metade); somar o piso de snipers no mesmo braço (é L3′, braço irmão — dois critérios de
uma vez impedem atribuir o efeito); tratar o R de §4 da KB-0107 como R de 30 min (é marcação de ~5 min,
[[11-KNOWLEDGE/KB-0113-ate-onde-as-series-acompanham-uma-aposta|KB-0113]]); ligar dinheiro real — 32 apostas/dia ×
0,05 SOL × 0,43 R × 0,5 ≈ **0,34 SOL/dia**, duas ordens de grandeza abaixo da
[[11-KNOWLEDGE/KB-0090-a-meta-em-dinheiro|meta de R$ 9 mil/dia]].

## Avaliação
_(append-only; o fechamento diário acrescenta uma seção datada por dia com aposta fechada)_

## Fontes

[[11-KNOWLEDGE/KB-0107-celula-lenta-como-porta-da-mesa|KB-0107]] §0–§8 (todos os números desta página) ·
[[11-KNOWLEDGE/KB-0104-taxas-base-sem-as-nascidas-cheias|KB-0104]] · [[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] §3 ·
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] ·
[[11-KNOWLEDGE/KB-0113-ate-onde-as-series-acompanham-uma-aposta|KB-0113]] ·
[[03-TRADING/Meme/Estudo-2026-09-16-tamanho-estagio-2|Estudo T4.29b (tamanho e participação)]] ·
`infra/scripts/sql/research/2026-09-16-r16-q01-porta-celula-lenta-r.sql` · `...-r16-q0{2,3}-*.sql` ·
`packages/risk-core/hunter_risk_meme/limits.py` · `docs/RISK_ENGINE_MEME.md`.
