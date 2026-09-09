---
tags: [experimento, regime, elegibilidade, populacao, mean-reversion, momentum]
updated: 2026-09-09
status: rascunho
owner: quant-engineer
exp: EXP-0020
strategy: "mean_reversion + momentum"
version: "mean_reversion v9 (de v6) + momentum v9 (de v8) — ainda não derivadas"
result: pendente
evaluable: 0
days: 0
last_eval: "—"
---

# EXP-0020 — o regime da hora como porteiro: `mean_reversion` só em lateral, `momentum` só em alta

> Rascunho para a Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/`. O número **EXP-0020** é a
> próxima vaga livre lida em 2026-09-09T02:40Z (23:40 BRT de 08/09); se outra tarefa tomar o número
> antes, renumerar. Nada aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`).
> **Estado em 2026-09-09 (BRT): o código está pronto e testado localmente; nada foi derivado,
> ativado ou replayado.** Os braços e os números abaixo são o desenho, não a medida.

## Hipótese (congelada antes de derivar)

Escrita no brief T3.52 e aqui **antes** de qualquer corrida:

> As duas famílias de estratégia do Lab supõem contextos opostos — `mean_reversion` compra o
> repique dentro de uma faixa, `momentum` compra a continuação de uma tendência — e hoje **as duas
> decidem em qualquer regime**, porque nada na decisão consulta `market_regimes`. Se a suposição de
> cada família for real, **cortar as decisões tomadas fora do regime dela deve melhorar a
> expectativa por operação sem que a melhora venha só de sorte de amostra pequena.**

**O que a hipótese explicitamente não promete, e o experimento tem de separar:** um portão só
**remove** decisões — a variante é, por construção, um **subconjunto** do pai. Então (i) a
comparação obrigatória é **pareada** sobre as decisões que sobreviveram (`t342-blocos/blocos.py`),
nunca médias soltas de populações de tamanhos diferentes; e (ii) uma melhora de média com população
menor é o resultado *esperado* de qualquer corte arbitrário — o que o EXP mede é se as decisões
**removidas** eram sistematicamente piores que as mantidas, e não apenas diferentes.

## Braços (dois, um por família; ambos derivados, nenhum por identidade)

| braço | versão | pai | portão | parâmetros |
|---|---|---|---|---|
| **G1** | `mean_reversion v9` | `mean_reversion v6` | `regime=btc:SIDEWAYS` | **idênticos ao pai** |
| **G2** | `momentum v9` | `momentum v8` | `regime=btc:BTC_BULL` | **idênticos ao pai** |

Nenhum parâmetro muda: `params_hash` da variante é o **mesmo** do pai, de propósito. É a primeira
vez que uma versão do Lab difere da anterior por algo que não é parâmetro — o que difere é a coluna
`strategy_versions.eligibility_policy` (`0017`, DATABASE.md §29), congelada pela ativação como
qualquer outro conteúdo.

## O corte, e por que ele não antecipa

A linha de regime que corta uma decisão é **a última hora fechada antes do corte da barra**
(`end_time <= source_bar_close`): uma decisão das 15:30 é cortada pela linha `[14:00, 15:00)`.
Registrado por inteiro em PIPELINE.md §4b item 10 — inclusive o ponto contra-intuitivo de que a
linha que *contém* o corte também não seria antecipação (ela é decidida com velas finais no início
da hora) e mesmo assim não é a usada. O replay aplica exatamente a mesma regra sobre a série
histórica de 31 dias, porque é o mesmo código (`decide.evaluate_slot`).

## O que o portão remove, e o que isso custa de população (a prever antes de medir)

Três motivos de recusa, todos declarados na avaliação (`ineligible`, `regime_gate:<RÓTULO>`):

1. **rótulo fora da lista** — a recusa que o experimento existe para medir;
2. **`UNKNOWN`** — aquecimento do classificador: **27 % das horas** dos 31 dias medidos na T3.43
   (207 de 745 horas do backfill saem em aquecimento). Essas decisões somem das duas variantes, e
   isso é custo, não sinal;
3. **hora ausente ou mais velha que 2 h** — buraco na série; também remove.

**Previsão a registrar antes da corrida:** a população de cada braço deve cair no mínimo os 27 %
do item 2, mais a fração de horas cujo rótulo não é o permitido. Se a queda medida for muito maior
que isso, o suspeito é a série (buracos), não a hipótese.

## Como julgar (a régua, escrita antes)

- **pareado por construção:** a variante é subconjunto do pai; comparar por
  `.claude/state/exp-drafts/t342-blocos/blocos.py` sobre as decisões comuns;
- **K1 (população mínima)** continua valendo: braço que não sobrevive ao K1 é **inconclusivo**, não
  negativo — e com um portão que remove ~1/3 das barras, K1 é o risco principal deste EXP;
- **passe de estresse** só se K1 sobreviver;
- **decomposição por regime**: cada decisão aceita grava no envelope
  (`supporting_features.provenance.regime_gate`) o rótulo, o id e a hora da linha que a liberou, e
  o ledger de replay grava o motivo de cada recusa — então o "quanto o portão tirou" é medido, não
  estimado.

## Passos (nenhum executado ainda)

1. deploy do commit da T3.52 (migração `0017` roda antes dos serviços);
2. `derive_variant.py … --policy regime=btc:SIDEWAYS --dry-run` e o irmão de `momentum`, depois sem
   `--dry-run`;
3. `activate_strategy_version.py` com `--purpose research_only`;
4. replay de 31 d × 4 mercados por braço, coorte própria;
5. avaliação pareada contra o pai; estresse se K1 sobreviver; veredito.
