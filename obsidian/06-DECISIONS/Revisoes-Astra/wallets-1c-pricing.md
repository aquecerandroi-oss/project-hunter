---
tags: [revisao-astra, meme, carteiras, pumpswap, motor-puro, precificacao, look-ahead, h-030]
date: 2026-10-05
updated: 2026-10-05
status: registro
owner: quant-engineer
decided_on: 2026-10-05
by: astra
tarefa: conserto da precificação de pool do motor 1c do H-030 (reserva virtual com sinal, pré-estado com a taxa LP) e ponte pura SwapRecord → Fill
veredito: rodada 1 APPROVE sem must-fix (3 nice-to-have aplicados); revisão de código APPROVE_WITH_NITS com 2 HIGH da Astra (pouso com pré-estado impossível, liquidez desconhecida no pareamento) e 1 MEDIUM (compra acima do orçamento), todos fechados
---

# Revisão da Astra: preço de pool do motor 1c e ponte `SwapRecord → Fill` (05/10)

Conserto do defeito que a própria Astra achou na rodada 2 de [[wallets-1a]] (item 2) e que estava em [[Open Bugs]], agora em [[Resolved Bugs]].
Conhecimento de origem: [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]]. Motor: [[wallets-engine]].
Bruto: `.claude/state/astra-review-wallets-1c-pricing.md`.

## O que foi revisado

Arquivos em `packages/indicators/hunter_indicators/meme/wallets/`:

- `tape.py`: `Reserves.virtual_quote_lamports` (com sinal), `effective_quote_lamports` e `Fill.lp_fee_lamports`.
- `pricing.py`: `pre_trade_state` (público) e a cotação de pool sobre `Q_real + V`, com teto do bruto no `Q_real`.
- `bridge.py` (novo): `SwapLike`, `PoolMints`, `BridgeRefusal` e `fill_from_swap`.
- `follow.py`: `pre_trade_real_sol` passa a usar o mesmo pré-estado.

Testes: `test_wallets_pricing_pool.py` (sintético), `test_wallets_bridge.py` (sintético) e `test_wallets_chain.py` (fixtures reais `t1a_*`, lidas pelo leitor do adaptador).

## Veredito

**APPROVE, sem must-fix.** Ela reexecutou os testes: 46 nos três arquivos novos e 144 nos de carteiras. Também percorreu as 13 fixtures em memória e achou 9 fills de pool, 3 `sol_is_base` e 1 registro de curva. Não reexecutou os 1 595 testes do pacote nem os 12 mutantes.

## Pontos que ela confirmou

| Ponto levado a ela | Leitura dela |
|---|---|
| (a) 3 de 13 swaps das fixtures são pools com **WSOL na base** e outro token na quote. A ponte recusa como `sol_is_base` | Confirmado. Recusar evita ler átomos de outro token como lamports |
| (b) O `SwapRecord` não traz a flag `complete` da curva, então a ponte exige `curve_complete` e recusa `curve_completion_unknown` | Correto. A ponte não inventa o estado de migração |
| (c) Teto da venda de pool = `Q_real` sobre o bruto | Concorda, como aproximação declarada. Não é o limite exato do cofre (`bruto − LP ≤ Q_real`) |
| (d) `V` constante através do trade | Confirmado nos dois pares fixados no motor. É suporte nesses casos, não prova universal |

## Nice-to-have, todos aceitos

1. **Teto com taxa diferente de zero.** Novo assert: a taxa sai **depois** do teto, então 1 SOL − 1,25 % dá 987 500 000, e não `min(líquido, 1 SOL)`.
2. **Procedência temporal de `curve_complete`.** A docstring da ponte diz que a flag tem de ser a **daquele evento**. Usar a flag de hoje em trades antigos seria look-ahead, e essa garantia é do chamador.
3. **"Recusa nunca é exceção".** A docstring agora separa as duas coisas:
   - recusa de **dado** é valor com nome;
   - erro do chamador (um `PoolMints` de outra pool, ou passado para registro de curva) levanta `ValueError`.

**O que ela faria diferente, também aplicado:** chamar o teto de **convenção de liquidação da pesquisa**, ao lado da fórmula, em `pricing.sell_lamports`.

## Divergências

Nenhuma.

## Relacionado

[[wallets-1a]] · [[wallets-engine]] · [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]] · [[carteiras-lucro-design]] · [[Resolved Bugs]] · [[EXP-M15-carteiras-vencedoras]]

## Revisão de código (code-reviewer + Astra, 05/10, noite): APPROVE_WITH_NITS, dois achados HIGH para ela, todos fechados

O `code-reviewer` aprovou com nits. A Astra, no mesmo diff, pediu mudanças com dois achados HIGH e um MEDIUM, todos reproduzidos (bruto: `.claude/state/astra-review-review-wallets-1c-pricing.md`). Isso **qualifica a aprovação da rodada 1** acima: ela não tinha olhado o que acontece **depois** que o pré-estado sai impossível. Tudo foi fechado nesta mesma mudança, com teste que falhou antes.

| # | Achado (cenário reproduzido) | Conserto |
|---|---|---|
| 1 HIGH | **Pouso cotado apesar de estado inconsistente.** Com pós-estado `Q_real` 1,5 SOL, `V` −1 SOL e compra de 1 SOL, o pré-estado sai impossível e era descartado em silêncio: `landing_sell(7, 10 tokens)` dava 5 000 000 lamports (4 937 500 com a taxa do teste) cotados só no pós-estado, quando o pior estado do slot é impossível de saber. O teste antigo exigia esse descarte | `MintTape.landing_states` devolve `CENSORED` quando algum trade do slot tem pré-estado impossível, e compra e venda no pouso saem censuradas. Um slot posterior sem trades continua no pós-estado do evento (§3.1). A ponte recusa esse registro como `pre_state_impossible`, então ele só chega ao motor por um `Fill` montado à mão |
| 2 HIGH | **Liquidez desconhecida virava zero.** `pre_trade_real_sol` devolvia 0 para pré-estado impossível, o que punha a aposta no tercil mais baixo e permitia pareá-la com um controle legítimo de baixa liquidez, contaminando o H2 | `pre_trade_real_sol` devolve `None` (desconhecido). No `pair_controls`, um gatilho com liquidez desconhecida fica sem par (`None`, contado como qualquer aposta sem par) e um controle assim nunca é sorteado. Também não pareia dois desconhecidos entre si (`None == None`) |
| 3 MEDIUM (preexistente) | **Compra de pool acima do orçamento.** Com `Q` 1 000 000 000, `B` 10¹², orçamento 50 000 000 e 125 bps, os átomos entregues custavam 50 000 001 lamports | Compra de pool em inteiros: a quote líquida é o piso de `orçamento × 10 000 / (10 000 + bps)` e os átomos são o piso do produto constante. Prova: líquida + taxa com teto ≤ orçamento, e custo com teto dos átomos ≤ líquida. Teste com três estados (incluindo `V` positiva e negativa). A curva continua no `quote_buy` do `curve.py`, que não foi tocado |
| nit | Registro de curva sem mint recebia o motivo `non_sol_quote` | Motivo próprio: `curve_mint_missing` |
| nit | `import` de `curve` dentro de uma função de teste | Movido para o topo do arquivo |

**Divergência de severidade, escrita:** a Astra classificou os itens 1 e 2 como HIGH e o `code-reviewer` como MEDIUM. Para o motor de hoje, que não lê fita real, o efeito é latente. Os dois foram fechados de qualquer forma, porque em produção dariam um resultado otimista (item 1) e contaminariam o controle do H2 (item 2) sem nenhum sinal.

**Mutação:** 6 mutantes novos, um por guarda nova, todos mortos: o `CENSORED` do pouso, o piso da quote líquida, o `None` da liquidez, o pulo do gatilho desconhecido, a recusa `pre_state_impossible` e o motivo `curve_mint_missing`. Os 12 da rodada 1 já estavam mortos.

**Sem achado novo dos revisores** sobre o fluxo com LP, a `V` com sinal, o teto da venda ou a ausência de look-ahead.
