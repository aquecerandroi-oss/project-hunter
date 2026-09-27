---
tags: [revisao-astra, meme, entrada, recuo, h-017]
date: 2026-09-27
updated: 2026-09-27
status: registro
owner: sexta-feira
decided_on: 2026-09-27
by: astra
tarefa: R82 — veredito formal da H-017 (recuo pequeno 3 %/60 s) com o controle do EXP-M25 (KB-0162)
veredito: H-017 concluída — NÃO CONFIRMA, no papel, entre os pares avaliáveis
---

# Revisão da Astra — R82 (o recuo pequeno empata com comprar na hora)

**No desenho** (`R82-design.md`, antes de abrir qualquer desfecho), a Astra concordou com:
- a ordem do rótulo;
- a leitura operacional da cláusula ambígua "não bate 'não comprar nada'": REFUTA (b) só com o IC superior do braço
  abaixo de zero, porque "não demonstrar superioridade não demonstra inferioridade". Pediu que se escrevesse que é a
  **aplicação do princípio** da errata do R76, e não uma definição que já estava na letra da H-017;
- a regra de parada: a 1.ª extração com ≥ 150 pares, e **todos** os pares dessa extração;
- o bootstrap emparelhado pelo moinho;
- o p de troca de sinal, só como descritivo.

**Must-fix aceito no desenho:** a fórmula `(1 + r_c)·p_c/p_gat − 1` **não é limite superior** e foi renomeada para
sensibilidade com saída fixada. Uma entrada mais barata pode bater o alvo antes de uma queda, ou sair por trailing
antes de uma recuperação.

**No veredito** (`R82-verdict.md`), concordou com `NÃO CONFIRMA`: n 151; D +0,0077 [−0,0269, +0,0410]; braço
contra "nada" −0,0385 [−0,0775, +0,0022]. Conferiu a regra cláusula a cláusula e recalculou do CSV os quocientes de
preço dos 74 pares de mesma foto.

**Três correções de redação aceitas** (nenhum número mudou):
1. o quociente de preço é fill ÷ gatilho − 1 = −1,98 %; o inverso tem média +9,21 %;
2. a sensibilidade de "preço de decisão" é **parcial**: as 27 não-entradas não são reprecificadas;
3. "as entradas não contribuíram positivamente para D nesta amostra", em vez de "não vem do preço". "O papel não
   escondeu melhora" vale só no agregado: em 30 de 74 pares o gatilho era mais barato que o fill.

**Aposentadoria:** a Astra concorda em **recomendar** ao orquestrador aposentar `recuo_v1/1` e `recuo_ctrl_v1/1`,
preservando os resultados. É decisão operacional dele. `NÃO CONFIRMA` não prova ausência de efeito nem autoriza
escrever REFUTA.

Nada rejeitado.

**Bruto:** `.claude/state/astra-review-R82-design.md` · `.claude/state/astra-review-R82-verdict.md`
**Relacionado:** [[KB-0162-o-recuo-pequeno-empata-com-comprar-na-hora|KB-0162]] · [[EXP-M24-entrada-no-recuo]] ·
[[EXP-M25-controle-do-recuo]]
