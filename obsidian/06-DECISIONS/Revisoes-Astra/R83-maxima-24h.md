---
tags: [revisao-astra, cripto, lab, maxima-24h, h-023]
date: 2026-09-28
updated: 2026-09-28
status: registro
owner: sexta-feira
decided_on: 2026-09-28
by: astra
tarefa: R83 — veredito formal da H-023 (proximidade da máxima de 24 h nos sinais do Lab de cripto) (KB-0163)
veredito: H-023 concluída — NÃO CONFIRMA na continuação; `_low` fica como pista
---

# Revisão da Astra — R83 (perto da máxima de 24 h não separa os sinais do Lab)

**No desenho** (`R83-design`, antes de abrir qualquer desfecho), a Astra concordou com:
- a janela `[obs − 1440 min, obs − 1 min]` de velas 1m finais, que é exatamente a da produção (`price.py:106`);
- as famílias (continuação = momentum, breakout, volume_anomaly, session_orb), com uma correção de redação: `trendline_bounce`
  é continuação pelo próprio contrato e "outras" é exclusão operacional, não classificação;
- os tercis **dentro de cada estratégia**, o indicador alto/baixo no moinho com o patamar julgado fora, a deduplicação
  por versão × mercado × barra com a prospectiva preferida;
- a errata da cláusula "IC inferior < −0,01 → REFUTA" pelo princípio do R76 (imprecisão não vira refutação).

**Três must-fix aceitos no desenho** (emenda §2b das notas, escrita antes de ler desfecho):
1. `received_at` é carimbo de persistência do banco, não a chegada no coletor → a guarda do moinho fica como **proxy**, e a
   conclusão é sobre a **reconstrução retrospectiva**, não sobre o que o scanner teria visto;
2. o p de permutação linha a linha não sustenta o Holm quando várias versões decidem a mesma barra → o p do portão virou o
   **maior** entre a permutação de episódios (estratégia, mercado, barra) e o p bilateral do bootstrap por mercado;
3. o rótulo H-023 é **externo** ao moinho: o moinho refuta com IC superior < MRE (+0,05), a fila com < +0,01. Antes da regra
   da fila entram as guardas de potência do moinho.

**No veredito** (`R83-verdict`), concordou com `NÃO CONFIRMA`: D −0,0324 R [−0,1131, +0,0376], p do portão 0,497, curva
ausente. Reproduziu em memória os dois contrastes (d_high e d_low), conferiu os md5 dos caches, 0 desfechos duplicados,
0 sinais sem desfecho, 0 mudança de disponibilidade de R entre a extração cega e a final, nenhum episódio com rótulo misto.
**Nenhum must-fix.**

Pontos de redação aceitos:
- registrar o **argumento literal para REFUTA** (−0,113 < −0,01) ao lado da errata;
- "a vantagem prevista de +0,05 R fica acima do IC superior **por mercado** (+0,038), logo não é sustentada por esse
  intervalo; o critério formal de refutação por tamanho não foi atingido" — o IC por dia [−0,132, +0,093] ainda comporta +0,05;
- momentum (+0,097) e volume_anomaly (−0,231) publicados **juntos**, como decomposição descritiva, não teste de interação;
- `_low` (+0,207, Holm 0,0004, melhor tercil −0,097 R) é **pista** para coorte nova; ρ 0,77 com ATR% não prova informação a mais.

Nice-to-have: um teste do intervalo IC superior ∈ [+0,01, +0,05) (moinho REFUTA × fila NÃO CONFIRMA) — acrescentado (18 testes);
o texto de previsão da seção `_low` na saída reaproveita o da máxima — só redação, registrado nas notas e não re-rodado para
não mudar as impressões digitais.

Nada rejeitado.

**Bruto:** `.claude/state/astra-review-R83-design.md` · `.claude/state/astra-review-R83-verdict.md` ·
`.claude/state/r83/astra_design.log` · `.claude/state/r83/astra_verdict.log`
**Relacionado:** [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab|KB-0163]] ·
[[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume|KB-0004]] · [[Fila de Hipoteses]]
