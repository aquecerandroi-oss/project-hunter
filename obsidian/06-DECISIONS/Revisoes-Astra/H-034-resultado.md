---
tags: [revisao-astra, meme, holders, progresso, resultado, h-034]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: quant-engineer
decided_on: 2026-10-07
by: astra
tarefa: R91 — resultado da H-034 (`holders_rising` e `progress_rising` isolados)
veredito: "concorda com H, P e família NÃO CONFIRMA; reproduziu h034.txt e sec.txt em memória e os hashes; 3 must-fix de descrição absorvidos sem mudar o rótulo"
---

# Revisão da Astra — resultado da H-034 (R91)

**Pedido:** revisar o código (`.claude/state/r91/stats91.py`, `freeze91.py`, `run91.py`, `sec91.py`, 17 testes em
`test_stats91.py`), a saída real (`h034.txt`, `sec.txt`) e a réplica SQL (`q_replica.sql`). Transcrição:
`.claude/state/astra-review-H-034-resultado.md`.

**O que ela confirmou:**

- Os três rótulos: H, P e a família terminam **NÃO CONFIRMA**. Nenhum defeito do código muda isso.
- Os testes passam (17), os hashes do pré-registro, das unidades e da lista elegível conferem, e `h034.txt` e
  `sec.txt` se reproduzem em memória sem nova consulta.
- O congelamento (04:55:32Z) precede a leitura dos desfechos (04:56:17Z).

**Três must-fix, absorvidos na KB e na Fila (só descrição):**

1. **O Holm composto não é Holm de hipóteses compostas.** O código aplica Holm em cada cenário e toma o máximo. Isso
   implementa "passar nos dois cenários", mas não garante controle familiar em geral. No caso sintético dela, o
   método dá 0,04 e o Holm sobre o máximo por medida daria 0,08. Declarado como limite; aqui não muda nada (Holm ≥ 0,15).
2. **P na pista de eventos não tem suporte.** O recorte por pista não reaplica ≥ 5 por braço; a pista de eventos de P
   tem 26 contra 2. Publicado como descritivo **sem suporte**. A pista de 15 s de P tem suporte.
3. **Publicar o Holm de S1 de P (0,35)** ao lado do primário (0,15).

**Nice-to-have, sem efeito neste dado:**

- As metades não recalculam o suporte ≥ 5. Ela recalculou e nenhum valor mudou.
- S1 imputaria −1 mesmo com `pnl_sol` nulo. Há zero casos.
- A réplica SQL não aplica as janelas de transição. O congelamento excluiu zero unidades.

**Leitura dela, que a KB segue:** as secundárias foram pré-registradas, então publicá-las todas não é seleção.
Destacar só a melhor seria. P na pista de 15 s tem IC nominal positivo; nas reais o IC inclui zero e os dois braços
perdem; `comprou_no_topo` 1,19× fica abaixo da previsão de 1,5×, mesmo no limite superior (1,37). Nada disso resgata
a família. Associação entre apostas admitidas não é efeito causal de tirar filtros. **Nada muda na mesa.**

Pré-registro: [[H-034-prereg]] · KB: [[KB-0190-os-dois-subindo-nao-separam-o-retorno]] ·
[[Revisoes-Astra/Index|índice]].
