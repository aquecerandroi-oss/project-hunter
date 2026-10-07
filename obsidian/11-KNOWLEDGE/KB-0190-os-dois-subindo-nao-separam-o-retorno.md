---
tags: [knowledge, meme, pesquisa, holders, progresso, porta, comprou-no-topo, hipotese, m4]
tema: holders subindo e progresso subindo, cada um sozinho e lido do que a porta gravou na decisão, não separam o retorno líquido das apostas de papel da porta fluxo_e_holders com a precisão pré-registrada; NÃO CONFIRMA nas duas
fonte: R91 (`.claude/state/r91/`) — H-034 da Fila de Hipóteses, origem na linha `holders_rising` / `progress_rising` isolados de Próximas Hipóteses (a)
fonte_url:
lido_em: 2026-10-07
evidencia: medição própria — 1 680 apostas de papel medidas (H, 10 estratos, 1 055 mints, 23 dias, 12/09–06/10) e 130 (P, 3 estratos, 109 mints, 18 dias) dos conjuntos operator/5, flow_v2/2–9, recuo_v1/1 e recuo_ctrl_v1/1; contraste ajustado por estrato com pesos de sobreposição; bootstrap de mint e de dia; réplica SQL independente
hipotese_testavel: sim
astra: concorda (duas revisões; 5 must-fix no pré-registro absorvidos numa emenda antes dos desfechos, 3 no resultado absorvidos sem mudar o rótulo)
status: vivo
owner: sexta-feira
updated: 2026-10-07
confiança: "?"
tipo: pesquisa
hipotese: H-034
variavel: holders_rising (H) e progress_rising (P) do bloco flow de meme_proposals.reasons, direção high (true selecionado)
populacao: apostas de papel measured, uma por (conjunto, mint), da porta fluxo_e_holders — H 1 680 (821 true / 859 false), P 130 (49 / 81)
efeito: H D_adj = +0,0274 por SOL; P D_adj = +0,133
ic: H [−0,030, +0,085]; P [−0,041, +0,315]
veredito: nao_confirma
proximo_passo: nenhum resgate com estes dados; H só volta com população nova em que o braço false seja medido sob a saída e a latência da mesa (as 123 posições reais da operator/5 deram +0,082 [−0,011; +0,173], descritivo); P só com coorte prospectiva onde progress_rising varie (hoje só os flow_v2/6–9, 143 unidades)
classe_de_perda: comprou_no_topo
mercado: meme
---

# KB-0190 — Os dois "subindo" não separam o retorno

> **H-034 (`holders_rising` e `progress_rising` isolados): `NÃO CONFIRMA` nas duas medidas e na família.**
> Estudo: código e saídas em `.claude/state/r91/` (`h034.txt`, `sec.txt`, `replica.txt`, `freeze.txt`).
> Pré-registro e emenda: [[Fila de Hipoteses]] § H-034. Revisões: [[H-034-prereg]] · [[H-034-resultado]].

## O que afirma

A porta da mesa exige "holders subindo" e "progresso subindo". A H-013 só tinha medido os dois **dentro** da
conjunção `equilibrio`, que morreu por limite de dado ([[KB-0155-o-equilibrio-quase-nao-passa-na-porta]]).
Aqui cada bit foi medido **sozinho**, como a porta o gravou no instante da decisão (bloco `flow` de `reasons`).

1. **Holders subindo (H):** as apostas com o bit verdadeiro rendem +0,027 por SOL a mais que as outras,
   no mesmo estrato. O intervalo vai de −0,030 a +0,085: não exclui zero nem o tamanho previsto (+0,05).
   - O braço verdadeiro **perde em nível**: −0,014 por SOL ajustado (−0,032 com o aluguel de ATA).
   - A segunda metade dos dias inverte o sinal (+0,057 na primeira, −0,016 na segunda).
2. **Progresso subindo (P):** +0,133 por SOL, intervalo de −0,041 a +0,315, com só 130 apostas.
   - É o mesmo caso de imprecisão previsto antes: poder só para efeitos perto de 0,19.
   - O nível do braço verdadeiro é +0,009 no primário e −0,104 no cenário S1.
3. **Nenhum dos dois é refutado.** Os dois intervalos sobem acima de +0,05. Não sabemos.

## Onde foi mostrado

- **Mesa de memes, papel, 12/09 a 06/10/2026.** Desfecho r = `pnl_sol` ÷ `entry.sol_spent`, como o simulador
  persistiu (1,75 %/perna mais o impacto da curva).
- **População:** a primeira aposta de cada par (conjunto, mint) da porta `fluxo_e_holders`: `operator/5`,
  `flow_v2/2`–`/9`, `recuo_v1/1`, `recuo_ctrl_v1/1`. A mesa exige os dois bits, então `operator/6` e `flow_v2/1`
  são 100 % verdadeiros e não entram no contraste.
- **O braço falso de H** é "estável" onde a porta só recusa a queda (`holders_rising_or_flat`), e "estável ou
  caindo" nos `flow_v2/6`–`/9`. O estrato (conjunto × regime dos parâmetros) separa as duas definições.
- **P só varia nos `flow_v2/6`–`/9`:** nos outros conjuntos o bit é sempre verdadeiro (a porta exige).
- **Antecipação:** o bloco `flow` bateu com a linha de `meme_features_15s` do mesmo instante em **993 de 993**
  unidades da pista de 15 s; nenhuma `features_end_time` depois da proposta. A pista de eventos monta a linha em
  memória e não tem fonte durável para conferir.
- Lista congelada às 04:55:32Z (sha256 `78cfa32d…`), desfechos lidos uma vez às 04:56:17Z.

## O que se mediu

| peça | resultado |
|---|---|
| H: D_adj, true − false (previsão ≥ +0,05) | **+0,0274**, IC mint [−0,030; +0,085], IC dia [−0,029; +0,094], Holm 0,19 (primário) / 0,35 (S1) |
| H: S1 (`indeterminate` = −1) | +0,0286, IC mint [−0,031; +0,087] |
| H: metades / deixa-um-fora | +0,057 / **−0,016** · deixa-um-fora entre +0,014 e +0,036 (todos positivos) |
| P: D_adj | **+0,133**, IC mint [−0,041; +0,315], IC dia [−0,057; +0,314], Holm 0,15 (primário) / 0,35 (S1) |
| P: S1 | +0,086, IC mint [−0,121; +0,293]; nível do braço verdadeiro −0,104 |
| réplica SQL no servidor | D_adj H 0,027369 e P 0,133387; nível do braço verdadeiro −0,013591 e +0,008968; iguais ao dígito |

**Secundárias pré-registradas** (não decidem; publicadas todas):

| secundária | H | P |
|---|---|---|
| `comprou_no_topo` (`pnl_sol < 0` e `high_water_x ≤ 1`), false ÷ true | 49,7 % × 41,9 % = **1,19×** [1,03; 1,37] (previa ≥ 1,5×) | 63,0 % × 55,1 % = 1,14× [0,82; 1,70] |
| perda ≥ 50 %, false ÷ true | 7,5 % × 9,5 % = 0,78× [0,47; 1,24] | 6,2 % × 10,2 % = 0,60× [0,09; 2,55] |
| só `operator/5` (papel) | −0,037 [−0,160; +0,081] (76 × 44) | — (sem contraste) |
| uma unidade por mint | +0,013 [−0,037; +0,064] | +0,127 [−0,039; +0,302] |
| pista de eventos | +0,003 [−0,059; +0,064] | +0,178 (26 × 2, **sem suporte**) |
| pista de 15 s | +0,056 [−0,035; +0,150] | +0,233 [+0,001; +0,442] (23 × 79) |
| P com nulo junto do falso | — | +0,071 [−0,114; +0,264] |
| **posições reais `operator/5`** (r = `pnl_sol` ÷ SOL gasto) | 68 × 55: −0,014 × −0,095, D **+0,082** [−0,011; +0,173] | — (2 falsos) |

## Por que importa

1. **Nada muda na mesa.** A mesa exige os dois bits. O que ela recusa não vira aposta, então não há contrafactual
   para "desligar" um critério ([[KB-0149-o-que-a-mesa-real-ensinou]] §5 item 28). E nenhum resultado aqui
   justifica apertar a porta (tirar o `holders_rising_or_flat`).
2. **O "estável" não aparece pior que o "subindo" no papel da mesa.** Dentro da `operator/5` o sinal é até
   contrário (−0,037), com intervalo largo.
3. **As reais da `operator/5` apontam para o lado da tese** (+0,082), com intervalo que toca zero e os dois braços
   perdendo. É a pista mais concreta para uma próxima hipótese, em dado novo e pré-registrado. Não é evidência.
4. **`comprou_no_topo` é um pouco mais frequente quando holders não sobem** (1,19×, intervalo acima de 1). Isso fica
   abaixo do previsto e não aparece no retorno.

## Por que pode falhar (limites desta nota)

- **Papel, não mesa.** A única série com a saída e a latência reais (123 posições) é a que mais se aproxima da tese,
  e o papel da mesma `operator/5` dá o sinal contrário. Não sabemos qual dos dois descreve a mesa.
- **Associação entre apostas admitidas, não efeito de tirar o filtro.** Os dois braços já passaram pelos outros
  critérios da porta.
- **P é minúsculo:** 130 apostas em três conjuntos de pesquisa. O IC positivo na pista de 15 s é um recorte de uma
  secundária, não um achado.
- **Holm composto:** o p de cada medida é o pior dos dois cenários depois de Holm em cada um. Isso não é controle
  familiar formal para hipóteses compostas (achado da Astra); aqui não muda nada, porque todos os p ficam ≥ 0,15.
- `recuo_v1/1` e `recuo_ctrl_v1/1` compartilham mints e instantes: o cluster de mint cuida da dependência, não do peso
  duplicado (com uma unidade por mint, H cai a +0,013).
- O regime dos parâmetros vem do histórico pelo `proposed_at` (aproximação declarada; 0 unidades nas janelas de
  transição).

## Segunda opinião (Astra)

- **Pré-registro** ([[H-034-prereg]]): 5 must-fix absorvidos na emenda das 04:52Z, antes dos desfechos. Foram o regime
  efetivo, o suporte e a censura operacionais, o Holm fixo, o estimador próprio e a unidade do retorno real. IC básico
  como decisório foi rejeitado e ficou como descritivo.
- **Resultado** ([[H-034-resultado]]): concorda com os três rótulos e reproduziu as saídas. 3 must-fix de descrição
  absorvidos: Holm composto declarado, P na pista de eventos marcado sem suporte, Holm de S1 publicado.

## Relacionados

[[Fila de Hipoteses]] (H-034) · [[Proximas Hipoteses]] · [[Dicionario de Variaveis]] ·
[[KB-0155-o-equilibrio-quase-nao-passa-na-porta]] (H-013) · [[KB-0108-anatomia-da-morte-depois-da-porta]] ·
[[KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[Perdas/comprou_no_topo]] · [[Mapa de Estrategias]] · [[KB-0188-a-concentracao-do-maior-comprador-nao-separa-o-retorno]]

## Revisão adversária (advogado de Jesus, 07/10/2026)

31 % das unidades de H (524 de 1 680) são **cópias exatas** de outra unidade. `flow_v2/2`, `/3` e `/5` repetem a mesma aposta (mesmo segundo, mesmo r) em 227 mints, e essa família leva ~45 % do peso. Contada uma vez, o D_adj de H cai a +0,008 [−0,040; +0,060], e a +0,012 [−0,046; +0,074] com o par recuo também colapsado. O rótulo não muda, porque os IC superiores continuam acima de +0,05.

Por isso o deixa-um-fora "todos positivos" **não é robustez**: sem a família, D = −0,019. As metades separam conjuntos, não tempo.

Nas reais da operator/5, 11 das 123 caem na janela em que a porta não exigia nada. Fora dela, D = +0,063 [−0,035; +0,165], com medianas iguais (−0,076 × −0,080), resultado puxado por quatro perdas de cauda no braço falso. Nas 108 entradas que também existem no papel, a ordem dos braços troca entre papel e real. **Não é pista; é ruído de execução.**

Lição de método (vale para toda pesquisa por conjunto): antes de pesar estratos por conjunto, conferir se conjuntos diferentes gravaram a mesma aposta (mint + r idênticos). Cópia não é réplica e anula o deixa-um-fora por conjunto. Ver [[Fila de Hipoteses]], H-034.

## Defensor (07/10/2026)

**Estimando estreito:** 91 % do peso de H foi "subindo × estável" e 54 % sob a saída de 30 min da `flow_v2`; a queda de holders quase não entrou. P é essencialmente o sinal de `mcap_delta_60s` e só varia na pista de 15 s. Proposta registrada na Fila: H-034b (gêmeo da `operator/6` sem a exigência), de valor baixo enquanto a mesa estiver pausada.
