---
tags: [knowledge, pesquisa, hipoteses, moinho]
updated: 2026-09-23
status: vivo
owner: sexta-feira
---

# Fila de Hipóteses

Fila do **moinho de hipóteses** (`infra/research/`, T4.87). Qualquer pessoa acrescenta um
bloco; o moinho lê esta página com `infra.research.queue.load_queue()` e a hipótese entra
na vez. Como escrever e como ler o veredito: `docs/RESEARCH.md`.

**Regras da casa** (de [[KB-0149-o-que-a-mesa-real-ensinou]] §5):

1. **Não girar botão das 13 variáveis já esgotadas.** Snipers, dev share, compradores
   únicos, progresso, fluxo do criador, idade, volume 1 m, sells/buys absoluto, holders,
   top10, retenção, carteiras novas e flip rápido: **nenhuma sobrevive** no R65 — que não
   é o mesmo que refutada ([[KB-0149-o-que-a-mesa-real-ensinou]]: *não confirmado ≠
   refutado*). Uma delas só volta com **população nova** ou **medida nova**, no `origem`.
2. **Resultado negativo é resultado.** `NÃO CONFIRMA` (não sabemos) e `REFUTA` (o efeito
   previsto não paga) ficam escritos aqui com o link para o relatório, e são coisas
   diferentes. Hipótese que morreu não volta com outro nome.
3. **Nada vai ao dinheiro real sem braço de papel pré-registado.** Um `CONFIRMA` do
   moinho é candidato a sombra, nunca parâmetro de mesa.

Formato de um bloco: `## <id> — <nome>` seguido de seis campos obrigatórios
(`origem`, `variável`, `população`, `previsão`, `refutação`, `status`).
Status: `aberta` · `em curso` · `concluída` · `arquivada`.

---

## H-001 — Absorção de uma venda grande (EXP-M22)

- **origem:** KB-0149 §6 item 2 · EXP-M22 · R62/[[KB-0143-o-que-antecede-o-dump]] (a venda grande é gatilho, não aviso)
- **variável:** `absorcao_30s` — recuperação do preço 30 s depois de uma venda ≥ 5 % da curva, em fração do tamanho da venda; direção `high`
- **população:** apostas de papel do Lab meme com pelo menos uma venda ≥ 5 % durante a vida da aposta; uma aposta por mint; export do `meme-worker`
- **previsão:** apostas em que o preço reabsorve ≥ 60 % da venda grande em 30 s rendem mais +0,05 por SOL arriscado que as demais
- **refutação:** limite superior do IC 95 % (bootstrap por mint) abaixo de +0,01 — abaixo disso a absorção não paga a ida-e-volta
- **status:** aberta

## H-002 — Retenção dos primeiros compradores (EXP-M19)

- **origem:** KB-0149 §6 item 2 · EXP-M19
- **variável:** `retencao_primeiros_20` — fração dos 20 primeiros compradores que ainda não venderam no instante da decisão; direção `high`
- **população:** decisões do Lab meme com fita de compradores reconstruída no instante da decisão; uma por mint
- **previsão:** decisões no tercil alto de retenção rendem mais +0,05 por SOL que o tercil baixo
- **refutação:** limite superior do IC 95 % abaixo de +0,01. Curva em pico (e não planalto) é **não confirmação**, não refutação
- **status:** aberta

## H-003 — Horizontes de 1 a 4 h no lado à vista

- **origem:** R68 parte B — `h = 240` ficou **inconclusivo** em 5 células (`partb_U2.txt` linhas 28–32: IC atravessando zero em todas) · KB-0149 §7 ("se existe vantagem em qualquer horizonte maior que 5 minutos")
- **variável:** os 5 preditores congelados do R68 (`P1_mom_prev`, `P2_revert_z`, `P3_vol_surge`, `P4_taker_imb`, `P6_breakout20`) em `h ∈ {60, 120, 240}`; direção `high` em cada score
- **população:** velas de 1 min dos mercados do universo U2, agregadas em barras completas; bootstrap de blocos de 3 dias, purga de `h` minutos
- **previsão:** pelo menos uma célula rende ≥ +0,10 % líquido por operação com Holm < 0,05 ao custo medido de 0,14 %
- **refutação:** limite superior do IC 95 % abaixo do MRE de +0,10 % em todas as células
- **status:** aberta

## H-004 — Percentil de `sells/buys` dentro da coorte viva

- **origem:** R69 teste A — `p=0,014` contra limiar BH de 0,0059 na família de 17; sobrevivente isolado, **não** confirmado (`.claude/state/r69/family.txt`); a variável absoluta está entre as 13 esgotadas do R65 (nenhuma sobrevive, o que não é refutação), o **percentil dentro da coorte** não está
- **variável:** `p_sb` — percentil de `sells_60s / buys_60s` do sujeito dentro da coorte viva no instante da decisão (sujeito fora da referência, empates a meio); direção `high`
- **população:** decisões do Lab meme com coorte viva de ≥ 20 mints observáveis; bootstrap de blocos de 60 min
- **previsão:** metade alta do percentil rende mais +0,05 por SOL que a metade baixa, e a curva de limiares é planalto
- **refutação:** limite superior do IC 95 % abaixo de +0,01 na população nova. Curva em pico é **não confirmação**
- **status:** aberta

## H-005 — Piso de impulso recente (`momentum_15m ≤ 2,0`)

- **origem:** [[Strategy Backlog]] item 7 · [[KB-0002-momentum-e-reversao-em-cripto]] — nunca medido neste recorte
- **variável:** `momentum_15m` no instante da decisão; direção `low`
- **população:** decisões persistidas do Lab (`strategy-worker` em sombra) com o envelope de features da decisão; cluster por mercado, estrato por dia
- **previsão:** decisões com `momentum_15m ≤ 2,0` rendem mais +0,10 R que as demais
- **refutação:** limite superior do IC 95 % abaixo de +0,02 R. O efeito sumir ao estratificar por ATR% é **não confirmação**
- **status:** aberta

## H-006 — Desequilíbrio agressor na barra do sinal

- **origem:** [[Strategy Backlog]] item 11 · [[KB-0014-taker-buy-volume-o-que-temos-medido]] — cobertura de 100 % medida, utilidade nunca medida
- **variável:** `taker_imbalance_5m` = `taker_buy_volume / volume` na barra da decisão; direção `high`
- **população:** decisões do Lab com velas de 1 min agregadas a 5 min (só barras completas); cluster por mercado, blocos de 3 dias
- **previsão:** o tercil alto rende ≥ +0,10 % líquido por operação acima do tercil baixo, ao custo medido de 0,14 %
- **refutação:** limite superior do IC 95 % abaixo do MRE
- **status:** aberta

## H-007 — Teto de volume relativo (exaustão)

- **origem:** [[Strategy Backlog]] item 12 · [[KB-0015-volume-relativo-e-o-pico-como-exaustao]] — o item declara explicitamente que nenhum edge foi prometido e o valor 12 é exploratório
- **variável:** `volume_ratio_5m` no instante da decisão; direção `low` (a hipótese é que volume relativo muito alto é exaustão)
- **população:** decisões do Lab acima do piso de volume atual (4×), para o contraste ser sobre o teto e não sobre o piso
- **previsão:** decisões com `volume_ratio_5m ≤ 12` rendem mais +0,10 R que as acima de 12, com planalto entre 8 e 16
- **refutação:** limite superior do IC 95 % abaixo de +0,02 R. Curva em pico é **não confirmação**
- **status:** aberta

## H-008 — Portão de tendência de 4 h

- **origem:** [[Strategy Backlog]] item 6 · [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] — transferência de horizonte não demonstrada; risco declarado de só encolher a amostra
- **variável:** `return_4h` no instante da decisão; direção `high`
- **população:** decisões do Lab com `return_4h` presente no envelope (censurar as sem, nunca tratar ausente como zero)
- **previsão:** decisões com `return_4h > 0` rendem mais +0,10 R que as demais
- **refutação:** limite superior do IC 95 % abaixo de +0,02 R. Fração censurada acima de 20 % invalida o estudo (população diferente), não refuta nada
- **status:** aberta
