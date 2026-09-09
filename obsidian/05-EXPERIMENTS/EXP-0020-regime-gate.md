---
tags: [experimento, regime, elegibilidade, populacao, mean-reversion, momentum]
updated: 2026-09-09
status: implementado, replay pendente
owner: quant-engineer
exp: EXP-0020
strategy: "mean_reversion + momentum"
version: "mean_reversion v9 (de v6) + momentum v9 (de v8) — ainda não derivadas"
result: inconclusivo
evaluable: 0
days: 0
last_eval: "—"
---

# EXP-0020 — o regime da hora como porteiro: `mean_reversion` só em lateral, `momentum` só em alta

> **Arquivada pela Sexta-feira em 2026-09-09** a partir do rascunho do `quant-engineer`
> (`.claude/state/exp-drafts/EXP-0020-regime-gate.md`, T3.52). O número **EXP-0020** foi confirmado
> livre na arquivagem. Nada aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`).
> **Estado em 2026-09-09: o portão de elegibilidade por regime foi implementado e entrou em
> produção** (migração `0017`, `strategy_versions.eligibility_policy`, commit `d21a11d` — T3.52/b/c)
> — **mas nenhuma das duas variantes deste EXP foi derivada, ativada ou replayada ainda.** Os braços
> e os números abaixo continuam sendo o desenho, não a medida.

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

**Nota de numeração (arquivamento):** `mean_reversion` e `momentum` já chegaram a `v10` por outro
eixo (o de timeframe, [[EXP-0021-timeframe]]) antes de este EXP derivar seus braços. `v9` continua
livre nas duas famílias (a `v9` do eixo de timeframe foi aposentada sem decisão e não reocupa o
número — `derive_variant.py` não reaproveita versões aposentadas), mas quem for derivar G1/G2 tem
de reconferir a próxima vaga livre no momento da corrida, não confiar neste número.

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

## O que já mudou desde o rascunho (T3.52/b/c, commit `d21a11d`)

O passo 1 dos "Passos" abaixo — o deploy do commit que implementa o portão — **já aconteceu**, e
trouxe duas peças que o rascunho original não previa:

1. **A janela de contexto passou a ser da versão, não do processo.** `required_context_minutes`
   por estratégia, piso `SHADOW_CONTEXT_MINUTES = 1560`, teto `SHADOW_CONTEXT_MAX_MINUTES = 6000`;
   a ativação recusa acima do teto com os números exatos. Isto não é deste EXP — é o mesmo commit
   que também resolveu o botão que travava [[EXP-0021-timeframe]] (a irmã `mean_reversion_h1_v1`
   passa a caber, com `context_minutes = 5880`).
2. **O worker recusa subir sem a migração `0017`.** Não há caminho para ativar G1/G2 numa VPS que
   não tenha a coluna `eligibility_policy` — o que fecha, por desenho, o risco de uma variante com
   portão decidir sem ele.

## Passos (ainda não executados)

1. ~~deploy do commit da T3.52 (migração `0017` roda antes dos serviços)~~ — **feito** (`d21a11d`);
2. `derive_variant.py … --policy regime=btc:SIDEWAYS --dry-run` e o irmão de `momentum`, depois sem
   `--dry-run`;
3. `activate_strategy_version.py` com `--purpose research_only`;
4. replay de 31 d × 4 mercados por braço, coorte própria;
5. avaliação pareada contra o pai; estresse se K1 sobreviver; veredito.

## Relacionadas

[[Experiments Index]] · [[KB-0079-onde-ganha-e-perde]] (o insumo que originou o portão) ·
[[EXP-0021-timeframe]] (o commit que destravou o contexto por versão é o mesmo) ·
[[Strategy Backlog]] · [[Registro de Tentativas]]

## Fontes

`.claude/state/notes-T3.52.md` (implementação do portão, se existir) ·
`infra/scripts/derive_variant.py` · `infra/scripts/activate_strategy_version.py` ·
`docs/PIPELINE.md` §4b item 10 · `docs/DATABASE.md` §29
