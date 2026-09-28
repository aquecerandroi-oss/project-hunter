---
tags: [revisao-astra, cripto, momentum, semanal, sobrevivencia, h-024]
date: 2026-09-28
updated: 2026-09-28
status: registro
owner: sexta-feira
decided_on: 2026-09-28
by: astra
tarefa: R84 — teste da H-024 (momentum semanal de série temporal em cripto grande, à vista, só compra) (KB-0166)
veredito: H-024 concluída — NÃO CONFIRMA (primária e secundária); nenhuma variante do Lab
---

# Revisão da Astra — R84 (evitar as moedas em queda de 14 dias não bate a cesta)

**No desenho** (`R84-design`, depois das regras de exclusão congeladas e antes de qualquer retorno), a Astra concordou
com: FRAX ficar (governança renomeada de FXS), ações tokenizadas não alavancadas ficarem pela regra literal com leitura
descritiva, ETFs tokenizados 2X/3X entrarem nos alavancados pelo desenho, último T = 14/09 (saída em vela final),
bootstrap de blocos móveis próprio (o do moinho reamostra grupos rotulados), p centrado, Holm por limite de deslistagem
e REFUTA só com os dois limites.

**Cinco must-fix aceitos no desenho** (notas §2, antes de olhar retorno):
1. "Inclui deslistados" não é censo completo → completude demonstrada contra **153 cópias históricas de cadastro** da
   Binance no Wayback (2017–2026): 0 pares USDT faltando, 6 491 checagens de cobertura sem falha; outras famílias do
   arquivo sem par fora. Critério "contagem monotônica" retirado (deslistagens reduzem contagem).
2. Fim de negociação ≠ fim do arquivo ≠ falha de aquisição → nenhuma série termina na fronteira mensal (31/08) e
   nenhum par `TRADING` sem vela recente; vela em formação cortada por `as_of` fixo.
3. Lacuna ≥ 14 d é alerta, não prova; marca carregada não é preço executável → 14 lacunas classificadas à mão (FTT,
   CVC, KEY, NBT: o mesmo ativo voltou; LUNA: outro ativo) e posição sem vela em T fica congelada, compra vira caixa
   (teste novo).
4. Migração com continuidade documentada não é perda total automática, e o limite pessimista não ordena TS − EW → 5
   ligações com a razão oficial (BCHABC→BCH, ERD→EGLD 1 000:1, LEND→AAVE 100:1, BNX→FORM, TON→GRAM).
5. Blocos contíguos no calendário → 0 buracos entre semanas avaliáveis.

**No veredito** (`R84-verdict`), concordou com `NÃO CONFIRMA` nas duas: rodou os 18 testes e **reproduziu o
relatório em memória** (D_ts +0,137 [−0,495; +0,864] / +0,150 [−0,481; +0,873]; D_cs +0,354 [−0,081; +0,696], Holm
0,044, patamar 7 d e 28 d negativos). **Nenhum must-fix de implementação.**

Correções de redação aceitas:
- não dizer "falta de poder" como causa única — "não confirmou; a precisão não exclui +0,25, e tamanho, patamar de
  7 d e corte antes de 2022 também falharam";
- a fumaça sintética não prova que o D_ts real é "quase só *timing* do fator comum" (o cenário "só transversal" também
  tinha persistência por moeda) — "nos cenários executados, a TS confirmou com o fator comum persistente; isso não
  identifica a origem do resultado real"; e "nenhum dos nulos executados confirmou";
- "negativo em 2019–2021, positivo desde 2022", não "contrariou a literatura" (dados até 2018, outro estimando; a
  diferença entre períodos não foi testada);
- D_cs: "pico observado na grade 7/14/28", não "artefato comprovado"; IC percentil e p centrado não são inversões um
  do outro — não escolher depois o procedimento favorável.

Nice-to-have: custo × posição congelada (o multiplicador global reduz implicitamente a posição presa) — **registrado
como ressalva**, erro ≤ 4·10⁻⁵ por semana, só na cesta (FTT), sensibilidade sem a ligação da FTT dá o mesmo D;
migrações não ligadas conferidas (só FTM→S seria candidata, e S não estava no top-20 nem com idade e volume próprios);
BTC comprado-e-segurado rotulado como **bruto** de custo.

**O que ela disse para não concluir** (aceito): que momentum semanal inexiste ou que +0,25 foi refutado; promover D_cs
pelo Holm; reabrir com 28 d, só pós-2022 ou outro universo; nível positivo como alfa ou viabilidade na Jupiter; dois
nulos como validação de tamanho/poder; porta para papel como aprovada (não foi avaliada).

Nada rejeitado.

**Bruto:** `.claude/state/astra-review-R84-design.md` · `.claude/state/astra-review-R84-verdict.md` ·
`.claude/state/r84/astra_design.log` · `.claude/state/r84/astra_verdict.log`
**Relacionado:** [[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta|KB-0166]] ·
[[KB-0164-momentum-semanal-em-cripto-grande|KB-0164]] · [[KB-momentum-semanal]] · [[Fila de Hipoteses]]
