---
tags: [experimento, meme, pumpfun, curva, pool, pumpswap, paper, pre-registro, moonshot, cauda, m4]
updated: 2026-09-12
status: pre-registrado
owner: quant-engineer
exp: EXP-M4
strategy: "meme/pumpfun — moonshot: a mesma porta da sonda de hype, alvo 10× (braço 1) e 25× (braço 2), trailing 50 % só depois de 3×, espera 2 h, posição que sobrevive à migração e é marcada pela fita da pool PumpSwap (carteira paper, sem ordem real)"
version: "gate sonda_de_hype v1 + saida alvo_10x_trailing_50_apos_3x_tempo_2h v1 (moonshot_v0/1) e alvo_25x_trailing_50_apos_3x_tempo_2h v1 (moonshot_v0/2), migração 0029"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-M4 — o braço moonshot: mega ROI, segurando através da migração

> **Pré-registro escrito na T4.11 em 2026-09-12 (13:xx BRT), ANTES de existir uma única proposta de
> `moonshot_v0/1` ou `moonshot_v0/2` e ANTES de existir uma única linha de `meme_trades` com
> `program = 'pump_amm'`.** Protocolo congelado; avaliações acrescentadas, nunca reescritas. Tudo em
> papel (`meme_paper_bets`, `mode = 'paper'`); sem chave, sem ordem real. Série `EXP-M<n>`, irmã da
> [[EXP-M1-comprar-cedo-na-curva]], da [[EXP-M2-a-linha-manda]] e da [[EXP-M3-sonda-de-hype]].

## Diretiva de origem

"pode colocar valores mais alto para sair num mega ROI, meme coin é diferente" (Everton, 12/09/2026).
Leitura: alvos de 2× cortam a cauda que paga em meme; o Lab precisa de um braço com alvos de 10×/25×,
espera longa e uma posição que **sobrevive à migração** para a PumpSwap — marcada pela fita da pool, não
vendida na conclusão da curva. Nada muda em `meme_paper_v0`/`trendline_v0`/`hype_probe_v0` (congelados:
continuam vendendo na migração).

## Hipótese (congelada) — e a hipótese nula que a página **prevê** confirmar

**H1:** entre as moedas que a porta da EXP-M3 aceita (30 s–5 min de vida, `hype_score ≥ 0,6`,
`dev_share ≤ 10 %` ou desconhecido com motivo, snipers ≤ 2, criador não vendedor líquido, participação
≤ 1 %), uma posição de 0,02 SOL segurada por até 2 h, através da migração, com alvo 10× (braço 1) ou
25× (braço 2), trailing 50 % armado só depois de 3× e saída `dead` (fita da pool muda ≥ 15 min com a
marca ≤ 50 % da entrada), produz expectância líquida positiva em SOL: **a cauda paga as perdas somadas**.

**H0 (a previsão desta página):** a cauda **não** paga as perdas somadas — a soma das apostas que morrem
(`dead`, `time_stop`, `creator_dump` com a marca perto de zero) excede o que os poucos 10×/25× devolvem,
e o resultado positivo, quando aparece, depende de **uma** aposta (leave-top-out negativo).

## Os dois braços (parâmetros congelados, semente da `0029`)

| | `moonshot_v0/1` (`…0005`) | `moonshot_v0/2` (`…0006`) |
|---|---|---|
| porta | `sonda_de_hype v1` — a mesma da EXP-M3, verbatim | idem |
| tamanho | 0,02 SOL | 0,02 SOL |
| alvo | **10×** (marca honesta ≥ 10 × gasto) | **25×** — o irmão de falseamento da cauda |
| trailing | 50 % do pico, **só depois de o pico chegar a 3×** (antes, sem trailing) | idem |
| espera | 7 200 s | 7 200 s |
| migração | `exit_on_migration = false`: segura; conclusão da curva idem | idem |
| `dead` | `mark_stale_s ≥ 900` **e** marca ≤ 50 % da entrada | idem |
| outras saídas | `creator_dump` (venda do criador na fita — curva **ou** pool), `time_stop` | idem |
| piso de perda | **nenhum** (`max_loss_pct = 100`, decisão declarada: um piso de 50 % venderia o drawdown que o moonshot existe para atravessar; `dead` é o piso) | idem |
| tetos | carteira 2,0 SOL, dia 0,20 SOL, **8 abertas**, 0,02 por mint | idem |
| taxas | entrada na curva 1,75 % (1,25 % + 0,5 % do caminho); saída na pool = faixa da PumpSwap pelo mcap do momento (1,25 % → 0,30 %) + 0,5 % do caminho + impacto | idem |

O braço 2 existe para falsear a cauda: se 25× nunca acontece dentro de 2 h, o braço 2 é o braço 1 com
mais `time_stop`/`dead` e menos alvo — e a diferença entre os dois mede quanto da expectância do braço 1
vem de alvos entre 10× e 25×.

## A marcação pós-migração (definição congelada, `pool_mark_sol` v1)

Depois de `meme_tokens.migrated_at`, a aposta é marcada pelo **último trade da fita da pool**
(`meme_trades`, `program = 'pump_amm'`) recebido até o minuto (`received_at <= tick`):

```
gross        = tokens × preço_do_último_trade          (preço = sol_lamports / token_amount, exato)
impacto      = min(gross / volume_SOL_dos_últimos_5_min × 100, 1 %)   (janela vazia → 1 %, motivo no_volume_5m)
faixa        = taxa da PumpSwap pelo mcap = preço × total_supply       (docs/PUMPFUN.md §4.1)
marca        = gross × (1 − impacto) × (1 − faixa − 0,5 % do caminho) − priority_fee
mark_stale_s = tick − último trade visto (ou a migração, se a pool nunca imprimiu)
```

A regra dispara num trade *k* e a venda é precificada no trade *k + 1* (`fill = next_trade`); sem trade
seguinte em 3 min: `dead` fecha a **zero** como `dead` (`fill = none`), qualquer outra razão fecha como
`rug_no_snapshot` com `pending_reason` (a doutrina §5: o resultado plausível é a aposta inteira).

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **REVISE** | O mecanismo é o da EXP-M3 (chegar antes do board) mais "não vender cedo". A vida mediana de uma criação é 0,01 dia e ≥ 17 % do volume é wash ([[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]]); a cauda existe (mints que graduam e sobem 10×+), mas a porta de hype não a seleciona melhor que o acaso — é exatamente o que a EXP-M3 mede |
| C2 | Sobreajuste | **PASS** | Nenhum parâmetro novo ajustado a dado: 10/25/3/50/7 200/900/50 vêm do brief; a porta é a da EXP-M3 |
| C3 | Amostra | **PASS condicionado** | A mesma cobertura da EXP-M3 (fita ~40 %); estimativa 5–50 apostas/dia; **migrações** dentro de 2 h: raras (a EXP-M1 mediu 43/49 graduações no slot da criação, mas isso é o slot, não a taxa) |
| C4 | Regime | **REVISE** | Hora UTC e dia; a cauda é ainda mais dependente de regime (sessão americana) |
| C5 | Saídas | **N/A → substituído** | Alvo, trailing armado, time stop, `dead`, `creator_dump`; risco = o gasto inteiro; **sem piso** (declarado) |
| C6 | Concentração | **PASS condicionado** | 2,0 SOL, 0,20/dia, 8 abertas × 0,02 = 0,16 SOL de exposição máxima |
| C7 | Execução | **REJECT para dinheiro real, PASS para papel** | A venda na pool a 1 % de impacto e na faixa de taxa é um teto otimista; MEV, tip, falha de transação e a liquidez real da pool **não** modelados; o `dead` a zero é o único pessimismo |
| C8 | Invalidação | **REVISE** | `dead` e `creator_dump` na pool; sem detector de rug nem de remoção de liquidez |

**Veredito do portão:** **`REVISE`** — 2026-09-12, quant-engineer (T4.11).

## Protocolo (congelado — nunca editar)

- **Conjuntos:** `moonshot_v0/1` (id `01994d00-6c1a-7000-8000-000000000005`) e `moonshot_v0/2`
  (`…0006`), semente da `0029`, `research_only`, `exp_ref = EXP-M4`; porta `sonda_de_hype v1`.
- **code_ref:** `hunter_indicators.meme.rules:evaluate_entry+evaluate_exit` — `exits.py`
  (`trailing_arm_multiple`, `hit_dead`), `pool.py` (faixas, impacto, cotação), laço em
  `services/meme-worker/hunter_meme_worker/{lab_bets_pool,pool_mark,lab_repo_pool}.py`.
- **Preço:** fill na primeira fotografia da curva posterior à decisão; na curva, venda na fotografia
  seguinte; na pool, venda no trade seguinte; `rug_no_snapshot`/`dead` a zero sem observação em 3 min.
- **Coorte:** prospectiva, os dois `rule_set_id`, a partir da primeira proposta na VPS (`‹pendente›`).
- **Régua (as duas do brief):** ≥ **100 apostas** fechadas **e** ≥ **30 dias**, por braço; expectância
  líquida em SOL com **IC 95 % por blocos de dia** (semente 20260912) acima de zero;
  **leave-top-out obrigatório:** sem a melhor aposta do braço, a expectância continua positiva? Sem
  isso, `descartar` mesmo com a média positiva.
- **Controle pré-declarado:** a própria EXP-M3 (mesma porta, alvo 3×, vende na migração) sobre os mesmos
  mints e dias: o Δ do braço 1 contra a sonda mede o que "segurar" acrescenta. Cláusula de identidade:
  se o Δ vier de ≤ 2 mints, o veredito é `descartar`.
- **Universo:** todo mint rastreado, sem filtro de sobrevivência; migrados incluídos por construção.

## Priors contrários, com número

1. Vida mediana 0,01 dia e ≥ 17 % de wash ([[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]]):
   a maior parte das apostas morre antes de 3× — e sem trailing antes de 3×, morre inteira.
2. Só uma fração pequena das criações gradua (o board `graduating` congela por minutos, T4.2c); um 10×
   a partir de 30 s–5 min de vida exige, na prática, a migração.
3. Pedágio: 1,75 % na entrada + até 1,75 % na saída (1,25 % da faixa inicial + 0,5 %) + 1 % de impacto —
   ~4,5 % por ida e volta antes de qualquer ganho.

## Previsões congeladas

- **P1 — a maioria morre:** ≥ 60 % das saídas do braço 1 por `dead`/`time_stop`; mediana de R ≤ −0,8.
- **P2 — o alvo é raro:** ≤ 3 % das apostas do braço 1 atingem 10×; ≤ 1 % do braço 2 atingem 25×.
- **P3 — expectância:** braço 1 entre −0,90 e −0,30 R (ponto **−0,60 R**); braço 2 pior que o braço 1
  em ≥ 0,10 R. **Veredito previsto: `descartar`** (H0).
- **P4 — leave-top-out:** se a média do braço 1 for positiva, sem a melhor aposta ela é negativa.
- **P5 — pós-migração:** ≤ 15 % das apostas chegam a ser marcadas pela pool (`mark_source = pool_tape`);
  entre as que chegam, mediana de `mark_stale_s` no fechamento > 300 s.

## Regra de sucesso (congelada)

`validada` (por braço) exige as seis da EXP-M1 **e** leave-top-out positivo **e** Δ contra a EXP-M3 > 0
sem identidade **e** ≥ 100 apostas em ≥ 30 dias. Qualquer coisa menos: `descartar`, com o conjunto
retirado no mesmo dia; a página fica.

## Regras de morte

- **K1** — cobertura da fita da pool: > 30 % das apostas migradas sem **nenhum** trade `pump_amm` em
  `meme_trades` nos 15 min seguintes à migração → o instrumento não vê a pool; parar e consertar.
- **K2** — > 30 % de censura. **K3** — fill sem fotografia posterior (impossível por construção).
- **K4** — expectância positiva vinda de < 3 mints. **K5** — uma aposta de `moonshot_v0` fechada como
  `migrated`/`curve_complete`: bug de laço (o conjunto não vende na migração), invalida a coorte.

## Avaliações (acrescentadas, nunca reescritas)

*Nenhuma.* A página nasce em 2026-09-12 com `result: nao-iniciado`, `evaluable: 0`, `days: 0`.

## Variantes tentadas

| Variante | Quando | Por quê | Onde |
|---|---|---|---|
| — | — | — | — |

## Relacionadas

[[Experiments Index]] · [[03-TRADING/Meme/README|Meme (Trading)]] · [[EXP-M1-comprar-cedo-na-curva]] ·
[[EXP-M2-a-linha-manda]] · [[EXP-M3-sonda-de-hype]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] ·
[[KB-0088-o-teto-de-participacao-nos-motores-de-backtest]]

## Fontes

`packages/indicators/hunter_indicators/meme/{pool,exits}.py` · `packages/indicators/tests/unit/{test_meme_pool,test_meme_exits_moonshot}.py` ·
`services/meme-worker/hunter_meme_worker/{lab_bets_pool,pool_mark,lab_repo_pool,lab_params}.py` ·
`services/meme-worker/tests/{test_pool_mark,test_lab_params_moonshot,test_lab_moonshot}.py` ·
`infra/migrations/versions/0029_meme_moonshot.py` · `docs/DATABASE.md` §41 · `docs/PUMPFUN.md` §4.1 ·
`docs/plans/T4-MEME-RADAR.md` §T4.11 · `.claude/state/brief-T4.11-moonshot-e-pos-migracao.md`.
