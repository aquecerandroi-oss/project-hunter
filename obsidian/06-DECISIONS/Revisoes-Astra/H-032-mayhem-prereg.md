---
tags: [revisao-astra, meme, mayhem, pre-registro, h-032, simulador]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: quant-engineer
decided_on: 2026-10-07
by: astra
tarefa: R89 — pré-registro da H-032 (moeda Mayhem depois da entrada, na sonda de recusadas do EXP-M23), antes de qualquer desfecho
veredito: "6 must-fix, todos absorvidos na emenda 1 antes da extração única; o portão do teto de SOL real (I2) nasceu do achado dela"
---

# Revisão da Astra — pré-registro da H-032 (R89)

**Pedido:** revisar o bloco congelado (`.claude/state/r89/prereg_frozen.md`, na [[Fila de Hipoteses]] desde
~00:33Z de 07/10). Até ali só se tinham visto contagens (`q_avail1–6.sql`). As perguntas foram: a sonda responde
à pergunta? Há confundimento nas outras recusas? O simulador é válido em curva Mayhem? Inferência, censura e
reuso do [[EXP-M23-desfecho-das-recusadas]]. Transcrição: `.claude/state/astra-review-H-032-prereg.md`.

**Seis must-fix, todos aceitos na emenda 1** (00:38Z, antes da extração única das 00:44Z):

1. **Alvo.** Cenário: Mayhem com retorno positivo, só menor que o das não-Mayhem. D sai > 0, mas excluir elimina ganho.
   - Correção: a H-032 virou **contraste descritivo** na sonda B, sem leitura de ganho marginal do veto.
   - A cláusula de nível foi declarada não aplicável, e o planalto também (variável binária).
2. **`n_outras` contaminada pelo Mayhem.** Cenário: `progress_*` falha por denominador indefinido em Mayhem e por fluxo ruim no controle. O tercil compara coisas diferentes.
   - Correção: `n_outras_limpa` sem `mayhem_*` e `progress_*` (`progress_unknown` só existe em Mayhem: 718 contra 0).
   - Entrou uma sensibilidade simétrica sem as famílias de volume e fluxo.
   - Suporte: falha com > 20 % de qualquer grupo descartado.
   - `refused_by` tem assinatura única (`operator/5+operator/6`), por isso não precisou de estrato.
3. **Instrumento Mayhem.** Ela leu que a primeira marca usa as reservas pós-compra e as seguintes usam a foto observada, cortada no SOL real **sem** o aporte da compra hipotética (`paper_fill.py:171` × `paper_engine.py:123`). Cenário: curva quase vazia leva a marca cortada e dispara perda sem movimento econômico.
   - Correção: portões I1 (bit), **I2 (teto em > 10 % das saídas Mayhem invalida)** e I3 (ida e volta recomputada).
   - A venda Mayhem on-chain foi declarada não validada.
4. **Inferência.** Cenário: Mayhem concentrada em horas com coleta pior, e a permutação individual destrói essa estrutura.
   - Correção: o estimador ajustado virou o primário, recalculado inteiro no bootstrap de blocos de 60 min, com p centrado.
   - Blocos de dia são exigidos; a permutação ficou só descritiva.
5. **Censura.** Cenário: as não-Mayhem ausentes eram grandes vencedoras e o IC superior cairia abaixo do MRE, levando a um REFUTA indevido.
   - Correção: REFUTA e CONFIRMA exigem os dois cenários extremos de imputação, e a ordem dos portões é instrumento → dado → suporte → rótulo.
6. **Nível × `docs/RESEARCH.md`.** Absorvido no item 1.

**Nice-to-have aceitos:** a conta de poder vira cenário ilustrativo. A auditoria do "um sorteio por mint" deu 2 478
propostas = 2 478 mints, 0 repetidos.

**Sobre o EXP-M23:** ela aceita o reuso com a declaração. A família e a parada originais ficam intactas.

**Errata de carimbo (minha, não dela):** os horários escritos à mão no bloco (00:45Z, 01:20Z) estavam errados. Os
reais, pelo relógio dos arquivos, foram registrados na Fila. A ordem pré-registro → revisão → emenda → desfechos se manteve.

Resultado e segunda revisão: [[H-032-mayhem-resultado]] · KB: [[KB-0189-o-papel-nao-sabe-medir-a-moeda-mayhem]].
