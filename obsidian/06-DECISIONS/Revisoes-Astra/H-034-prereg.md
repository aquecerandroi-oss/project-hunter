---
tags: [revisao-astra, meme, holders, progresso, pre-registro, h-034]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: quant-engineer
decided_on: 2026-10-07
by: astra
tarefa: R91 — pré-registro da H-034 (`holders_rising` e `progress_rising` isolados na hora da decisão)
veredito: "desenho defensável como associação entre o bit gravado e o retorno das primeiras apostas admitidas; 5 must-fix aceitos numa emenda datada (04:52Z) antes de qualquer desfecho"
---

# Revisão da Astra — pré-registro da H-034 (R91)

**Pedido:** rever o bloco congelado às 04:44Z (`.claude/state/r91/prereg_frozen.md`, sha256 `abde5ab4…`, na
[[Fila de Hipoteses]]) com as contagens cegas (`r91/avail0.txt`–`avail3.txt`) e cinco perguntas: o estimador e o p,
a seleção da unidade e a mistura "estável" × "estável ou caindo" no braço `false`, a população, os mínimos, e o que
faltava declarar. Transcrição: `.claude/state/astra-review-H-034-prereg.md`. Nenhum desfecho tinha sido lido.

**Cinco must-fix, todos aceitos na emenda 1 (04:52Z):**

1. **O histórico de parâmetros não prova o regime usado.** A pista de eventos renova a configuração uma vez por tique
   do Lab (`event_gate_caches.py:122`). Cenário: uma proposta logo depois da mudança ainda roda a configuração antiga.
   Feito: regime pelo `proposed_at` declarado como aproximação; as unidades da `operator/5` nas duas janelas de
   transição (até 15 min depois da última chave) saem e são contadas. Foram 0.
2. **Suporte e censura operacionais.** Cenário: um estrato suportado perde todo um braço depois de tirar as
   `indeterminate`. Feito: universo fixado na lista congelada; pesos com as unidades que entram em cada cenário;
   estrato sem braço cai e os pesos se renormalizam; metades com fronteira comum; deixa-um-fora vazio impede o CONFIRMA.
3. **Holm fixo em {H, P} e proteção também do CONFIRMA.** Cenário: tirar P por limite de dado transforma o Holm em
   teste único. Feito: medida fora entra com p = 1; IC finito e ≤ 1 % de réplicas inválidas valem para os dois rótulos.
4. **O estimador do R88 não serve intacto.** Ele fixa pesos por tamanho e invalida réplicas. Feito: estimador próprio
   (`r91/stats91.py`), com multiplicidade dos clusters sorteados e pesos n_true·n_false/n recalculados na réplica,
   testado com 17 séries sintéticas antes da extração.
5. **Unidade do retorno real.** O texto dividia por lamports. Feito: r real = `pnl_sol` ÷ (`sol_spent_lamports` ÷ 10⁹).

**Nice-to-have:**

- Aceito: declarar que `progress_rising` não é sempre `true` na pista de eventos e publicar o suporte por pista.
- Aceito: tratar as contagens cegas como preliminares e declarar o efeito de desenho suposto no poder.
- **Rejeitado: IC básico como decisório.** Ficou o percentil, como registrado. A conjunção com o p centrado já protege,
  e o básico é publicado ao lado; os dois deram o mesmo lado de zero em todos os casos.

**Onde ela concorda:** pesos de sobreposição, p = maior dos dois p centrados, Holm fixo, primeira aposta sem troca,
nulo separado de `false`, exclusão da sonda de recusadas, S1 como cenário, nível lucrativo, metades e deixa-um-fora.

Resultado: [[H-034-resultado]] · [[KB-0190-os-dois-subindo-nao-separam-o-retorno]] · [[Revisoes-Astra/Index|índice]].
