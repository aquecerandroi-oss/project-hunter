---
tags: [knowledge, meme, entrada, recuo, hipotese, metodo, papel, m4]
tema: esperar um recuo de 3 % em até 60 s depois da aprovação da porta empata com comprar na hora, no papel e com controle emparelhado (H-017 não confirma); as duas políticas perdem dinheiro em nível
fonte: R82 (`.claude/state/notes-R82.md`) — H-017 da Fila de Hipóteses, controle do EXP-M25
fonte_url:
lido_em: 2026-09-27
evidencia: medição própria — 151 pares resolvidos (26/09 15:05Z → 27/09 21:11Z), braço de papel `recuo_v1/1` contra o controle de entrada imediata `recuo_ctrl_v1/1` na mesma decisão (mint, t0), bootstrap por mint 10 000 (moinho), regra de parada congelada antes dos desfechos, 20 testes sintéticos
hipotese_testavel: sim
astra: concorda (desenho e veredito; 1 must-fix de desenho e 3 de redação, todos aceitos)
status: vivo
owner: sexta-feira
updated: 2026-09-27
confiança: "?"
tipo: pesquisa
hipotese: H-017
variavel: politica de entrada com recuo de 3% em ate 60s (recuo_v1) contra entrada imediata em t0 (recuo_ctrl_v1)
populacao: 151 armacoes de recuo_v1/1 (1a por mint) com par resolvido de recuo_ctrl_v1/1 na mesma decisao, 26-27/09, papel
efeito: D (braco - controle) = +0,0077 por SOL decidido; braco contra nada -0,0385
ic: D [-0,0269, +0,0410]; braco [-0,0775, +0,0022]
veredito: nao_confirma
proximo_passo: bracos recuo_v1/1 e recuo_ctrl_v1/1 podem ser aposentados (decisao do orquestrador); a pista do preco de entrada volta so com execucao real no gatilho
classe_de_perda: comprou_no_topo
mercado: meme
---

# KB-0162 — O recuo pequeno empata com comprar na hora

> **H-017 (recuo pequeno como melhora de preço): `NÃO CONFIRMA`**, no papel, com o controle emparelhado do
> [[EXP-M25-controle-do-recuo]]. D = **+0,77 pp** por SOL decidido, IC [−2,69, +4,10]; a previsão pedia ≥ +2 pp com o
> IC acima de zero. O braço perde para "não comprar nada" (−3,85 %, IC [−7,75, +0,22]).
> Estudo em `.claude/state/notes-R82.md` · código e saídas em `.claude/state/r82/` · pré-registo em
> [[Fila de Hipoteses]] § H-017 · protocolos em [[EXP-M24-entrada-no-recuo]] e [[EXP-M25-controle-do-recuo]].

## O que afirma

Depois que a porta aprova uma moeda, esperar que o preço recue 3 % da máxima (em até 60 s) antes de comprar **não
rende mais** do que comprar logo, nas mesmas decisões. A diferença medida é pequena (+0,77 pp por SOL) e o intervalo
cobre zero. As duas políticas perdem dinheiro em nível: o braço −3,85 % por SOL, o controle −4,62 %.

A pista que sobrou da H-016 ([[KB-0157-esperar-o-recuo-nao-paga]]: +2,28 pp no papel, na mesma população em que foi
achada) **não se repetiu em coorte nova**.

## Onde foi mostrado

**Desenho.** Cada armação de `recuo_v1/1` (a 1.ª por mint) foi emparelhada com a aposta de `recuo_ctrl_v1/1` na
mesma decisão. O controle é o mesmo documento de parâmetros **sem** as duas chaves do recuo, e entra em `t0`.
- Métrica: `r = pnl_sol ÷ SOL gasto`. Não recuou ou morreu na rechecagem = 0 no braço.
- Parada congelada antes de abrir desfechos: a 1.ª extração com ≥ 150 pares resolvidos. Às 21:26Z havia **151**.
- Assinaturas `md5(params)` dos dois conjuntos iguais às do deploy, sem nenhuma edição registrada.

| | n | valor [IC 95 %] |
|---|---|---|
| **D = braço − controle (primária)** | **151** | **+0,0077 [−0,0269, +0,0410]** |
| braço contra "não comprar nada" | 151 | −0,0385 [−0,0775, +0,0022] |
| controle contra "não comprar nada" | 151 | −0,0462 [−0,0914, +0,0015] |
| 26/09 (UTC) | 68 | D +0,0000 [−0,056, +0,052] |
| 27/09 (UTC) | 83 | D +0,0141 [−0,031, +0,055] |
| blocos de 6 h (6 blocos) | 151 | D +0,0077 [−0,0272, +0,0380] |
| sem o maior par (BULA-KUN) | 150 | D +0,0146 [−0,0172, +0,0460] |

Braço melhor em 47 pares, pior em 30, **igual em 74**. Σ braço −0,407 SOL contra controle −0,488 SOL.

**Cláusula a cláusula:**
- 151 ≥ 150, logo não é limite de dado.
- O limite superior de D (+4,10 pp) passa de +1 pp, logo não refuta um efeito de +2 pp.
- D = +0,77 pp < +2 pp e o IC contém zero, logo não confirma.
- "Não bate nada": a média do braço é negativa, logo a leitura literal dispara. Mas o IC alcança +0,22 pp. A
  operacionalização declarada antes dos desfechos (o princípio da errata do R76: imprecisão não vira refutação)
  exige o IC superior do braço abaixo de zero para refutar. Sozinha, dá `NÃO CONFIRMA`.

## De onde vem o D

| parte | n | contribuição para D | média no grupo |
|---|---|---|---|
| entrou na **mesma foto** de fill do controle | 74 | **0,0000** | 0,0000 (retorno idêntico em 74/74) |
| entrou numa foto posterior | 50 | −0,0014 | −0,0043 |
| morto na rechecagem (`pullback_killed`) | 16 | **+0,0106** | +0,0997 |
| não recuou (`no_pullback`) | 11 | −0,0014 | −0,0190 |

- **A contribuição positiva líquida vem das 16 mortes na rechecagem:** o controle perdeu −10 % em média nelas, e só
  2 das 16 ganharam. As entradas não contribuíram positivamente nesta amostra.
- A maior morte **custou** uma vencedora: BULA-KUN, morta por venda do criador 0,86 s depois de `t0`, rendeu +102,5 %
  no controle.
- As 11 que não recuaram renderam +1,9 % no controle, e 5 delas ganharam. É o mesmo padrão da H-016: as que não
  recuam não são as piores.

## A ressalva do papel, medida

O papel preenche na **primeira foto depois da decisão**. Controle: foto a p50 6,3 s de `t0`. Gatilho do braço: p50
5,2 s. Por isso **74 de 124 entradas (59,7 %)** caíram na mesma foto do controle, com o mesmo preço e o mesmo
retorno. O R79 tinha visto 22 de 34.
- **O papel não escondeu uma melhora de preço, no agregado.** Nos 74 de mesma foto, o preço marginal da foto ficou em
  média **1,98 % abaixo** do preço do gatilho (o gatilho no denominador): o preço segue caindo depois do gatilho.
  Houve melhora apagada em **30 de 74** pares, os casos em que o gatilho era mais barato que a foto.
- **Onde o papel mediu o preço, o preço melhor não virou retorno.** Nas 50 de foto posterior, o controle pagou em
  média 6,8 % a mais que o braço (mediana 4 %), e D nesses pares foi −0,4 pp.
- **O gatilho nem sempre é mais barato que `t0`:** acima de `t0` em 53 de 124 (a moeda subiu e recuou 3 % da nova
  máxima). Mediana gatilho ÷ `t0` = 0,98.
- **Sensibilidades com a saída fixada** (aproximação proporcional; não simulam o motor e não são limites; sem peso no
  rótulo):
  - mesma foto ao preço do gatilho: D +0,0008 [−0,047, +0,053];
  - parcial, preços de decisão nas 124 entradas (braço no gatilho, controle em `t0`; as 27 não-entradas como
    observadas): D −0,0237 [−0,060, +0,010].
- **Papel × real não é mensurável nesta coorte.** A mesa real não aceitou nenhuma destas decisões (op5: 139
  expiradas, 13 recusadas), então não há par real. A leitura de nível é de papel. O R79 mediu papel × real no op5 como
  +0,002 [−0,087, +0,086] (n 38).

## O que se aprendeu

1. **O "+2 pp de preço" do R77 era da população em que foi achado.** Em coorte nova, com controle na mesma decisão,
   ficou +0,77 pp com IC que cobre zero. É a quarta leitura da entrada que não separa as vencedoras (R65/R67,
   H-016, H-019 [[KB-0159-a-desaceleracao-nao-avisa-o-topo]], agora H-017).
2. **Um controle `research_only` de entrada imediata resolveu o emparelhamento.** A proposta do controle existiu em
   152 de 154 decisões; as 2 faltas são as previstas (`already_open` pela pista de 15 s). Com a sombra do op5 tinham sido 39 de 171. O
   desenho serve para qualquer braço de entrada futuro.
3. **Um papel com resolução de uma foto não mede melhora de preço de segundos.** Seis de cada dez entradas caem na mesma
   foto do controle. Uma hipótese de preço de entrada precisa de execução no gatilho (real ou simulada troca a troca),
   não do motor de fotos.
4. **A rechecagem no gatilho foi a única parte que ajudou**, e custou uma vencedora grande (BULA-KUN). Isso não é
   hipótese confirmada: são 16 casos e o intervalo não foi medido para essa parte.

## Hipótese testável no Lab

**Nenhum braço novo.** A H-017 não confirma, e a pista do preço só volta com medida nova: fill no preço do gatilho
(execução real, ou replay troca a troca com pouso realista) e população nova. A recomendação ao orquestrador é
**aposentar `recuo_v1/1` e `recuo_ctrl_v1/1`**, preservando os resultados. É decisão operacional dele. `NÃO CONFIRMA`
não prova que o efeito não existe, e esta nota não o afirma.

## Por que pode falhar (limites desta nota)

- **Dois dias de papel** (26–27/09): nenhuma posição real na coorte.
- **Seleção por resolução.** Ficaram fora 3 decisões (2 sem controle e 1 `indeterminate`), todas com mais de 20 h na
  extração. Se as apostas problemáticas ficam abertas por mais tempo, ficam sub-representadas (Astra).
- **O IC é largo nos dois sentidos.** O limite superior (+4,10 pp) não exclui o efeito previsto de +2 pp, e por isso
  o rótulo é `NÃO CONFIRMA`, não `REFUTA`.
- **O p de troca de sinal (0,67) é só descritivo.** As duas políticas não foram aleatorizadas.

## Segunda opinião (Astra)

- **Desenho** (`.claude/state/astra-review-R82-design.md`): concordou com a ordem do rótulo e com a leitura
  operacional de "não bate nada". Must-fix aceito: a fórmula de saída fixada não é limite superior e foi renomeada
  para sensibilidade.
- **Veredito** (`.claude/state/astra-review-R82-verdict.md`): concorda com `NÃO CONFIRMA` no papel. Três correções de
  redação foram aceitas: a direção do quociente de preço, a sensibilidade parcial e a atribuição da decomposição.
  Concorda com a recomendação de aposentar os braços como decisão do orquestrador.
- Síntese em [[R82-recuo-controle]].

## Relacionados

[[Fila de Hipoteses]] (H-017) · [[EXP-M24-entrada-no-recuo]] · [[EXP-M25-controle-do-recuo]] ·
[[KB-0157-esperar-o-recuo-nao-paga]] · [[KB-0159-a-desaceleracao-nao-avisa-o-topo]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[Mapa de Estrategias]]
