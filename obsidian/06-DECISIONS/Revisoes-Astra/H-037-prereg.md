---
tags: [revisao-astra, meme, carteiras, copia, pre-registro, h-037]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: quant-engineer
decided_on: 2026-10-09
by: astra
tarefa: pré-registro do H-037 (copiar ~20 carteiras no papel, EXP-M28)
veredito: "REQUEST_CHANGES antes de T0 com 6 must-fix (interrupção depois de olhar o placar, algoritmo inferencial e degeneração, conjuntos disjuntos, denominadores dos portões, escopo do REFUTA com censura, exclusões de concentração). Todos foram aceitos na emenda 1 (04:58Z); a colisão do funil apontada no diálogo entrou na emenda 2 (05:09Z). A Astra conferiu os seis reparos no diálogo (rodada 3) e fechou com DECISÃO CONJUNTA (rodada 4). X não foi testado"
---

# Revisão da Astra: pré-registro do H-037

**Pedido.** Revisar o bloco H-037 da [[Fila de Hipoteses]], registrado às 04:45Z de 09/10. A cópia congelada está
em `.claude/state/h037/prereg_frozen.md`, com sha256 `a6ce641b…`, e a Astra conferiu que ela bate com a Fila. A
fonte bruta é `.claude/state/astra-review-H-037-prereg.md`. O experimento é o
[[EXP-M28-copiar-carteiras-no-papel]], e o diálogo do desenho é [[Dialogos/copy-paper|copy-paper]].

## Os 6 must-fix e onde foram resolvidos

| # | Achado (com o cenário de falha dela) | Resolução |
|---|---|---|
| 1 | Uma mudança pedida depois de olhar o placar encerrava só as entradas. Um resultado favorável no dia 15 permitiria CONFIRMA numa janela escolhida pelo resultado | Emenda 1 item 2: interrupção → NÃO CONFIRMA ("coorte interrompida"), só descrição |
| 2 | O WCB-t estava incompleto e não havia regra de degeneração. Retornos todos iguais dão 0/0 | Emenda 1 item 6: fórmulas, LD só sobre células observadas, `default_rng(20261009)`, pesos de Webb, t* restudentizado, quantis `higher`/`lower`, > 1 % de réplicas inválidas ou EP zero → degenerado → NÃO CONFIRMA |
| 3 | Primário e S1 não eram disjuntos: uma cópia contaminada e lucrativa entraria duas vezes | Emenda 1 item 3: M e U particionam F; S1 e S2 substituem os valores de U; maturação em T0 + 28 d + 2 h |
| 4 | Os denominadores dos portões permitiam leituras diferentes (só lacunas abertas, horas duplicadas, unidades misturadas) | Emenda 1 item 4: união das lacunas por líder com as globais, todas as registradas, só o estrato `regra`; falha de confirmação contada por cópia |
| 5 | O REFUTA ignorava a censura: 10 % censurados por migração com +0,50 esconderiam uma média completa acima do MRE | Emenda 1 item 5: o REFUTA vale só para as cópias medidas e é exigido em M e em S2 (U no percentil 90 de M); portão \|U\|/\|F\| > 10 % |
| 6 | "Sem o melhor líder e sem o 1 %" podia ser lido como dois testes ou como um cumulativo | Emenda 1 item 7: dois testes separados, com desempates fixos |

**Nice-to-have aceitos.** A conta de poder passou a ser chamada de aproximação do teste simplificado: EP de 0,0267 a
0,0246 e efeito detectável de 0,07 a 0,08, números que a Astra reproduziu. O α é local, declarado. Ficou declarado
também que nenhuma descoberta secundária vira primária.

**Concorda com:** T0 ligado à readiness, seleção anterior a T0, uma tentativa por mint e estrato, invalidadas no
primário, a ordem instrumento → dado → REFUTA → CONFIRMA, o estrato do Everton à parte e nada em dinheiro real.

## Relacionado

[[EXP-M28-copiar-carteiras-no-papel]] · [[Dialogos/copy-paper|copy-paper]] ·
[[2026-10-09-piloto-copiar-carteiras-no-papel]] · [[Revisoes-Astra/Index|índice das revisões]]

## Emenda 3 (troca da regra de escolha)

Revisão curta às 05:35Z (`.claude/state/astra-review-H-037-emenda3.md`): **sem must-fix**. A emenda 3 é coerente com o registro e com as emendas 1–2 (estratos, `include ≤ 4`, mínimo de 10 líderes, T0 depois da gravação). A troca está registrada honestamente como revisão depois de exposição às listas dos dois dry-runs, sem escolha entre listas. A regra antiga não aparece como requisito vigente no desenho. Os nice-to-have (“até 4” e “≤ 24” nos resumos, e a precisão de “antes de qualquer escolha” como “antes da seleção definitiva”) foram aplicados. A regra da tarefa B foi revisada em [[copy-leader-selection]].
