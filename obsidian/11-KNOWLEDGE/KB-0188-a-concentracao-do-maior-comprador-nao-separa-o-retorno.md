---
tags: [knowledge, meme, pesquisa, concentracao, maior-comprador, e2b, golpe, hipotese, m4]
tema: excluir as entradas em que uma carteira concentra o SOL da curva (fatia do maior comprador) não melhora o retorno líquido do papel meme; a concentração alta associa-se a mais saídas `creator_dump`, sem pior retorno
fonte: R88 (`.claude/state/r88/`) — H-031 da Fila de Hipóteses, origem na linha `top_buyer_share` / `fill_seconds` de Próximas Hipóteses (a)
fonte_url:
lido_em: 2026-10-07
evidencia: medição própria — 1 647 apostas de papel da pista de eventos com a fita da decisão (`0062`), 1 300 mints, 24/09–06/10; 192 apostas `flow_v2/6`–`/10` com o `pedigree_e2b`, 132 mints, 17/09–06/10; contraste ajustado por conjunto com bootstrap de mint e de dia; réplica SQL independente
hipotese_testavel: sim
astra: concorda (duas revisões; 5 must-fix no pré-registro, 4 no resultado — todos absorvidos)
status: vivo
owner: sexta-feira
updated: 2026-10-07
confiança: "?"
tipo: pesquisa
hipotese: H-031
variavel: top_buyer_share (pedigree_e2b, A) e largest_net_buyer.share_of_real_sol (decision_tape, B), direção low
populacao: apostas de papel measured, uma por (conjunto, mint) — B 1 647 (6 conjuntos da pista de eventos), A 192 (flow_v2/6–9)
efeito: B D_adj = −0,0023 por SOL; A D_adj = +0,086
ic: B [−0,043, +0,037]; A [−0,075, +0,248]
veredito: nao_confirma
proximo_passo: reabrir só com posições reais com fita e fatia > 0,35 em número suficiente (hoje 6), contraste pré-registado antes; a variável de estoque da H-010 segue não testada
classe_de_perda: golpe_do_criador
mercado: meme
---

# KB-0188 — A concentração do maior comprador não separa o retorno

## O que afirma

A tese da H-031 era que, quando uma carteira concentra o SOL comprado na curva, a moeda é armadilha
(classe [[golpe_do_criador]]), e excluir essas entradas melhora o retorno. **No papel, isso não apareceu.**

- Com o instrumento bom (a fita da decisão, `decision_tape`, livro desde o nascimento provado), o braço
  com fatia ≤ 0,35 rende **o mesmo** que o braço com fatia > 0,35: D ajustado por conjunto −0,0023 por SOL.
- A concentração alta **associa-se** a mais saídas `creator_dump` (45,8 % contra 21,7 %), mas o retorno
  não piora, e as perdas ≥ 50 % são **menos** frequentes no braço alto (1,8 % contra 5,6 %).
- A medida literal da linha de origem (`top_buyer_share` do `pedigree_e2b`) é **truncada**: a própria
  E2-b recusa ≥ 0,35 antes de a proposta nascer, então só existe entre 0,05 e 0,23. `fill_seconds` é
  nulo em todas as propostas (a curva ainda não encheu quando a proposta nasce).

## Onde foi mostrado

- **Mesa de memes, papel, 17/09 a 06/10/2026.** Desfecho r = `pnl_sol` ÷ `entry.sol_spent`, como o
  simulador do Lab persistiu (taxa de 1,25–1,75 % por perna, mais o impacto da curva e a faixa da
  PumpSwap depois da graduação).
- **B:** 1 647 apostas `measured` de 6 conjuntos da pista de eventos (`absorb_v0/1`, `absorb_v0/2`,
  `flow_v2/1`, `operator/5`, `recuo_v1/1`, `recuo_ctrl_v1/1`), 1 300 mints, 11 dias. Unidade = a
  primeira proposta do par (conjunto, mint) que gerou aposta. Guardas: captura aceita, livro "desde o
  nascimento" provado, ≥ 10 carteiras (proxy de participantes).
- **A:** 192 apostas `measured` de `flow_v2/6`–`/9`, 132 mints, 18 dias.
- Lista congelada (sha256 `18dcd185…`) **antes** de ler qualquer desfecho.

## O que se mediu

| peça | resultado |
|---|---|
| B: D ajustado, baixo − alto (previsão ≥ +0,05) | **−0,0023**, IC mint [−0,043; +0,037], IC dia [−0,025; +0,025] (20,8 % de réplicas inválidas), Holm 0,60 |
| B: curva de limiares 0,20 → 0,45 | **ausente**: D ≤ 0 nos 6; em 0,25, −0,040 [−0,079; −0,002] (sentido contrário, um ponto só) |
| B: S1 (`indeterminate` = −1) | +0,029, IC mint [−0,022; +0,082] |
| A: D ajustado no quantil 2/3 (0,1222) | **+0,086**, IC mint [−0,075; +0,248], Holm 0,28, metades +0,15/−0,16, pico; S1 +0,015 |
| B: saída `creator_dump`, alto ÷ baixo | **2,11×** (+24,1 pp, IC [+18,3; +30,0]) |
| B: perda ≥ 50 %, alto ÷ baixo | **0,32×** (1,8 % contra 5,6 %) |
| réplica SQL independente de B | 1 647 unidades, D_adj −0,002302, D agrupado −0,003923 (ao dígito) |

**Veredito: `NÃO CONFIRMA`** nas duas medidas e na família. Em B a cláusula de intervalo do REFUTA
seria atingida no primário (+0,037 < +0,05), mas a trava de réplicas inválidas bloqueia o REFUTA e o
cenário S1 não a atinge. O moinho agrupado (descritivo) diz REFUTA — não é o veredito.

## Por que importa

1. **Um teto de concentração nas mesas não tem base.** A E2-b ([[EXP-M9-pedigree-e2b]]) já recusa
   ≥ 0,35 no `flow_v2/6`–`/10`; a medida do instante da decisão não mostra que essas moedas rendam pior.
2. **A concentração parece prever o criador vendendo, não a perda.** O excesso de `creator_dump` vale
   também quando o maior comprador **não** é o criador (46,6 % contra 20,5 %; exploratório, depois de
   correr). Uma explicação possível — **não demonstrada** — é que a saída `creator_dump`, sempre ligada,
   já tira a aposta antes do despejo no simulador.
3. **O que a H-010 deixou aberto continua aberto.** Ela pediu a variável de **estoque** de tokens
   (`largest_holder.share_of_supply`); esta nota mediu o **fluxo líquido** de SOL, outra operacionalização.

## Por que pode falhar (limites desta nota)

- **Papel, não mesa.** A saída do simulador vê a venda do criador e sai; a mesa real tem latência e,
  no SIMFTR (H-014), não havia bloco para pousar antes. As 6 posições reais com fatia > 0,35 tiveram r
  médio −0,254 contra −0,029 em 50 — anedota, mas no sentido da tese. É por aí que se reabre.
- **A depende de uma mint.** Uma mint nos quatro conjuntos tem fatia exatamente igual ao limiar; no braço
  baixo (a regra ≤) o D é +0,086, no alto seria +0,020.
- **O bootstrap de dia perdeu 20,8 % das réplicas** (conjuntos que vivem 2–5 dias somem da réplica com
  pesos fixos). Os intervalos de dia condicionam-se às réplicas válidas.
- **Metades com composição diferente:** o código recalcula suporte e pesos em cada metade; a 2.ª metade
  de A só tem `flow_v2/9`.
- `ledger.wallets ≥ 10` conta carteiras que só venderam: é proxy de participantes, não de compradores.
- O corte de propostas foi 07/10 00:00Z, não o instante do congelamento.

- **Advogado de Jesus (07/10):** a fatia de B sobe quando o criador vende (o denominador `real_sol` cai), então concentração e venda prévia do criador estão misturadas. Entre os criadores que ainda não tinham vendido, o excesso de `creator_dump` é 1,58×, não 2×. O papel sai na primeira venda do criador; a mesa real perdeu −0,67 e −0,77 em duas dessas moedas.
- **Defensor (07/10):** o braço baixo em −0,055 torna o CONFIRMA inalcançável abaixo de D ≈ 0,2. A direção do viés papel × real no `creator_dump` é desconhecida, e o `exit_on_creator_dump` está nulo nas 1 889 apostas. Próximo passo útil: o conjunto gêmeo sem `creator_dump`, em coorte nova.

## Segunda opinião (Astra)

- **Pré-registro** ([[H-031-prereg]]): 5 must-fix absorvidos na emenda das 00:36Z, antes de qualquer
  desfecho — contraste ajustado por conjunto, p que respeita a dependência por mint, guarda declarada como
  proxy, censura com cenário decisório, rótulo da família (REFUTA só com A e B refutando).
- **Resultado** ([[H-031-resultado]]): concorda com NÃO CONFIRMA; reproduziu o sha256 e as duas contas do
  empate de A; 4 must-fix de redação/descrição absorvidos (metades, "neutraliza" → associação,
  denominador da perda ≥ 50 %, corte temporal).

## Relacionados

[[Fila de Hipoteses]] (H-031) · [[Proximas Hipoteses]] · [[Dicionario de Variaveis]] ·
[[KB-0153-o-maior-comprador-nao-estava-no-arquivo]] (H-010) ·
[[KB-0156-o-despejo-em-bloco-nao-e-uma-rede-de-financiamento]] (H-014) ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[EXP-M9-pedigree-e2b]] · [[golpe_do_criador]] ·
[[Mapa de Estrategias]]
