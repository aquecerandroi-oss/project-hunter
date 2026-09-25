---
tags: [experimento, meme, pumpfun, paper, pre-registro, organica-lenta, migracao, m4]
updated: 2026-09-16
status: pre-registrado
owner: sexta-feira
exp: EXP-M7
strategy: "meme/pumpfun — orgânica lenta: entrar tarde (3–30 min), com a curva entre 10 e 30 % e subindo, holders ≥ 20 subindo, top-10 ≤ 30 %, sem sniper, e segurar pela migração"
version: "gate organica_lenta v1 + exit alvo_5x_trailing_40_apos_2x_tempo_60m_segura_migracao v1 (organic_v0/1, migração 0035, relógio de minuto)"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
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

# EXP-M7 — orgânica lenta: entrar depois do pump dos bots e segurar pela migração

> **Pré-registro escrito na T4.22 em 2026-09-13 (01:xx BRT), ANTES de existir uma proposta do conjunto.** Protocolo
> congelado; avaliações acrescentadas pelo fechamento diário, nunca reescritas. É a E3 do
> [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas|estudo das 21 apostas]]. A previsão padrão é `descartar`.

## Diretiva de origem

O dia 12/09 fechou **35 apostas de papel medidas a −9,4 R**; em **31 de 35 a moeda nunca valeu mais do que no
momento da compra** (`high_water_x ≤ 1,0`) e o criador despejou em 22. Todos os conjuntos vivos compram 30–300 s
depois da criação — o topo do pump dos bots. A lição medida do fechamento (M-L2): entrar com < 5 % da curva rendeu
−0,36 R a menos (IC 95 % fora de zero). O plantão (runs 3/5/9/13) mediu que ~75 % das graduações acontecem no mesmo
segundo da criação e que as **lentas** (compradas organicamente) têm `bo` > 0 e top-10 alto no início; a única regra
publicada em memes é positiva **só** pela cauda (Kamat, run 12). O Everton (13/09 01:0x): "então aprimore essa parte".

## Hipótese (congelada)

**H1:** entrar **tarde** — na série de minuto, 3–30 min depois da criação, quando a curva cruza 10–30 % e sobe, com
≥ 20 holders subindo, top-10 ≤ 30 % (lido ≥ 3 min após a criação, M-D5), snipers ≤ 2, dev ≤ 10 %, criador não
vendedor líquido, exclusões E2 — e **segurar pela migração** (alvo 5×, trailing 40 % armado após 2×, 60 min, piso 50 %)
rende expectância **positiva** porque só as moedas com compra orgânica sustentada chegam a esse ponto. **H0
(previsão):** a cauda existe mas é rara demais para 100 apostas em 30 dias; o resultado fica entre −0,30 e +0,10 R
(ponto −0,10 R) → `descartar`.

## Definição congelada (`organic_v0/1`)

| critério | limiar | recusa |
|---|---|---|
| idade | 180–1 800 s | `age_below_min` / `age_above_max` |
| progresso da curva | 10–30 % **e subindo** (minuto contra o anterior) | `progress_below_min` / `progress_above_max` / `progress_not_rising` |
| fluxo | líquido > 0, ≥ 5 compradores no minuto, vendas/compras ≤ 0,8 | `flow_not_positive` / `buyers_below_min` / `sells_ratio_above_max` |
| holders | ≥ 20 **e subindo** | `holders_below_min` / `holders_not_rising` |
| top-10 | ≤ 30 % (`meme_features_1m.top10_share`, o `t10` do site) | `top10_above_max` / `top10_<motivo>` |
| snipers | ≤ 2 | `snipers_above_max` / `snipers_unknown` |
| dev | ≤ 10 %, desconhecido recusa | `dev_share_above_max` / `dev_share_unknown` |
| criador | não vendedor líquido, desconhecido recusa | `creator_is_net_seller` / `creator_net_seller_unknown` |
| pedigree | E2 (criador em série, clone) | `creator_serial` / `symbol_clone` |
| participação | ≤ 1 % do volume do minuto | `participation_above_cap` |

Saídas: alvo **5×**, trailing **40 %** armado só após **2×**, `max_hold_s` 3 600, `creator_dump`, piso 50 %;
**`exit_on_migration = false`** — a posição atravessa a conclusão e a migração e passa a ser marcada pela fita da
pool ([[05-EXPERIMENTS/EXP-M4-moonshot|T4.11]]). Tamanho 0,05 SOL; 3 abertas. Placar só com desfechos `measured`.

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **PASS** | Compra tardia numa curva que já provou demanda sustentada; segurar pela migração é a única forma de capturar a cauda |
| C2 | Sobreajuste | **REVISE** | Dez limiares do estudo, nenhum ajustado a dados de apostas; o fechamento diário mede cada um |
| C3 | Amostra | **REVISE** | Poucas moedas chegam a 10–30 % com holders ≥ 20: contar recusas por dia antes de julgar |
| C4 | Regime | **REVISE** | A fração de graduações lentas muda com o dia e mudou com o upgrade de 12/09 |
| C5 | Saídas | **PASS** | Alvo, trailing armado tarde, tempo, dump e piso — nenhuma saída "pela fotografia ausente" conta |
| C6 | Concentração | **PASS** | 3 abertas, 0,05 SOL, ≤ 1 % do volume |
| C7 | Execução | **REVISE** | Fill no minuto seguinte (relógio de 1 min): a latência é conhecida e medida (`decision_to_fill_s`) |
| C8 | Invalidação | **PASS** | A régua: ≥ 100 apostas e 30 dias, IC 95 % por blocos de dia, leave-top-out; menos que isso, `descartar` |

## Previsões (congeladas)

- **P1** ≥ 70 % das recusas nos 7 primeiros dias serão `progress_below_min`/`holders_below_min` (a maioria nunca chega lá).
- **P2** ≤ 5 propostas por dia.
- **P3** ≥ 50 % das apostas fechadas sairão por `creator_dump` ou `max_loss` mesmo assim.
- **P4** R médio entre −0,30 e +0,10 (ponto −0,10) → `descartar` (H0); só ≥ +0,20 R com leave-top-out ≥ 0 muda a previsão.
- **P5** ≥ 1 aposta atravessará a migração e será marcada pela pool nos 7 primeiros dias.

## Adendo — 15/09/2026 17:3x BRT (plantão run 20; não altera o protocolo)
- **Unidade do progresso:** `curve_progress_pct` é a **fração de tokens vendidos** da curva, não a fração de SOL levantado; a janela 10–30 % desta regra corresponde a ≈ **2,39–8,55 SOL** levantados (parecer da Astra), não 8,5–25,5 SOL como uma leitura ingênua sugeriria. A regra não muda; a interpretação sim.
- **Taxas-base externas para comparar (referências, não teto — M-P40):** SmugCalls por evento on-chain: graduação 2,62 % de todas as moedas, 4,15 % das que passam de 1 SOL, 6,71 % das que passam de 10 SOL, 12,40 % das que passam de 25 SOL; mediana criação→graduação 5 min entre as graduadas. MELT: 73 % das migradas caem abaixo de 40 % do topo em 20 min.
- **As lições de 13/09 (snipers > 2, top-10 médio) não replicaram em 14/09** (M-D14) — os braços 3 e 4 seguem como pré-registrados (`descartar`) e serão julgados só pela régua.

## O que NÃO fazer
Ajustar os limiares olhando os primeiros dias (KB-0092); ligar dinheiro real nisto antes da régua.

## Avaliação
_(append-only; o fechamento diário acrescenta uma seção datada por dia com aposta fechada)_

### Avaliação 2026-09-16 (T4.27, 02:3x BRT) — Mayhem excluído desde 16/09 (T4.27)

**Fato medido (banco da VPS, 3 dias, `2026-09-16-t427-picos-sao-mayhem.sql`):** todos os 95 picos de `mcap_sol` ≥ 500 SOL
foram moedas Mayhem — o agente empurra a reserva *virtual* de SOL sem SOL entrar (KAT: 23,9 → 1 977 SOL em 60 s, 5 holders).
**O que muda nesta página, sem tocar no protocolo congelado:** (1) o portão deste experimento recusa moeda Mayhem por padrão
(`exclude_mayhem: true` gravado nos `params` dos conjuntos vivos por `meme_rule_set.py --set-param exclude_mayhem=true --all-active
--apply`, auditado em `system_events`; recusas `mayhem_curve` / `mayhem_unknown`); (2) a marca de papel de qualquer aposta em Mayhem
passa a ser limitada ao SOL real da curva (`RISK_ENGINE_MEME.md` §6) e as fechadas antes disso viram `indeterminate` com motivo
`mayhem_virtual_sol` (`meme_reclassify_mayhem.py`, dry-run por padrão); (3) `mcap_executable_sol` nasce ao lado do `mcap_sol` nas duas
séries (`0042`). **Leitura para o veredito:** toda aposta desta página em moeda Mayhem fechada antes de 16/09 sai do placar medido —
o número de apostas medidas pode cair; nenhum limiar foi mexido. Braço que quiser Mayhem de propósito diz `exclude_mayhem: false`
(nenhum hoje). Detalhe em [[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] §5.

## Fontes
`packages/indicators/hunter_indicators/meme/{rules,rules_criteria}.py` (`max_top10_share`) ·
`packages/indicators/tests/unit/test_meme_rules_organic.py` · `services/meme-worker/hunter_meme_worker/{lab_repo,lab_models,proposals}.py` ·
`infra/migrations/versions/0035_meme_organic_e3.py` · `docs/DATABASE.md` §47 · `docs/plans/T4-MEME-RADAR.md` §T4.22 ·
`docs/RISK_ENGINE_MEME.md` §10.11 · [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas]] · [[09-OPERATIONS/Diario-Meme/2026-09-12]].
