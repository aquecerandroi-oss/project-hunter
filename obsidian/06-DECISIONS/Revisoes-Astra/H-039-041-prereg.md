---
tags: [revisao-astra, b3, win, mercado-tradicional, pre-registro, h-039, h-040, h-041, arnes-retrospectivo]
date: 2026-10-17
updated: 2026-10-17
status: registro
owner: quant-engineer
decided_on: 2026-10-17
by: astra
tarefa: "três estratégias intradiárias no WIN pedidas e aprovadas pelo Everton em 17/10/2026: pré-registro H-039/H-040/H-041 na Fila, arnês retrospectivo em infra/research/b3/ e runbook de exportação do MT5"
veredito: "pré-registro — rodada 1: 8 must-fix, 7 aceitos, a permutação mantida como discordância registrada; rodada 2: ela aceitou a discordância e pediu 2 correções de censura, aplicadas como escritas; congelado às 21:51:04Z. Código — rodada 1: 7 must-fix, todos corrigidos (um deles, a seleção 'sem dado', resolvido por emenda 1 em vez de mudar a população); rodada 2: 1 must-fix (réplicas livres), corrigido"
---

# Revisão da Astra — pré-registro de H-039/H-040/H-041 e o arnês retrospectivo do WIN

**Pedido:** revisar, antes do congelamento, o rascunho das três hipóteses da família intradiária do WIN —
H-039 (rompimento da faixa dos 30 minutos iniciais), H-040 (reversão de 15 minutos) e H-041 (rompimento depois de
contração de amplitude) — e depois o código que as executa sobre o histórico de 1 minuto que o Everton vai exportar
do MT5 da Rico. Origem: pedido do Everton de 17/10/2026; fontes [[EXP-0010-session-orb-faixa-de-abertura]],
[[KB-0082-reversao-de-15-minutos-o-sinal-e-o-fluxo]], [[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]];
contra o prior [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]], [[KB-0080-candlestick-evidencia]],
[[KB-0149-o-que-a-mesa-real-ensinou]] e [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]]; disciplina copiada
da H-038/H-038r ([[Revisoes-Astra/H-038-prereg|H-038-prereg]]).
Fontes brutas: `.claude/state/astra-review-H-039-041-prereg.md`, `-prereg-r2.md`, `-code.md` e `-code-r2.md`; cópia
congelada, rascunhos, emenda e manifesto em `.claude/state/h039-041/`.

**Congelamento:** 2026-10-17 21:51:04Z, antes de existir qualquer export do MT5 (nenhuma barra do WIN ou do Ibovespa foi
lida por nós). `prereg_frozen.md` sha256 `a4887cdae6ffc529b0e12c44f997e45a1f70f4bac151cb3942f25e84c9a8c37c`; o bloco
anexado à [[Fila de Hipoteses]] é byte a byte essa cópia. **Emenda 1** às 22:55:36Z (ainda sem dado), sha256
`b01dc273dd7aaa7c03a9b85bfb60ff6140ae048dd7d9577585728ce273f65876`, inserida no bloco da H-039.

## Pré-registro, rodada 1 — 8 must-fix

1. **Permutação de lados com geometria espelhada não testa a estratégia inteira** (no ORB e na caixa, o instante de
   entrada depende da direção). Ela propôs um nulo de inovações OHLC embaralhadas entre dias. **Mantive** a permutação
   de lados, agora estratificada (H-040: mês × posição da barra), com o escopo declarado no texto: associação
   **condicional aos instantes e à geometria selecionados**; quem responde "a média líquida é > 0" é o IC. Motivo: o nulo
   de inovações exigiria uma segunda implementação vetorizada das três regras só para a permutação (risco de o que
   testa divergir do que decide), e a H-038r usa permutação de sinal com instante fixo. **Discordância registrada; na
   rodada 2 ela a aceitou** como tal.
2. **A trava "censura não resolvida bloqueia CONFIRMA" da H-038r tinha sumido**, e um minuto faltante podia apagar um
   stop. → censura só por carimbo (qualquer minuto faltante entre a entrada e a saída), igual nos dois lados, e a trava
   voltou.
3. **Patamares sem fórmula** (25 barras de 30 num vizinho de 15 min; grade e teto da H-040 para 10 e 30 min). →
   ⌈5L/6⌉ barras; grade [O+Δ, 16:30−Δ] e 390/Δ − 1 operações.
4. **Convenções de execução abertas** (stop inválido, precedência, arredondamento do alvo, "depois" da saída). → tabela
   de precedência, alvo arredondado para longe da entrada, igualdade toca, janelas `[t, t+5 min]`.
5. **Base da H-041 incompleta** (recuar ou não, barras parciais, B = 0, vizinhos de k). → 20 pregões imediatamente
   anteriores, ≥ 15 valores, sem recuar, atravessa o corte; A = 0 ou B = 0 sem decisão; vizinhos recalculam A e B.
   Ela confirmou que usar o primário como base do primeiro dia do holdout **não** é antecipação.
6. **"Grade comprovada por carimbo" era afirmação demais.** → O = 10:00 BRT passou a **suposto**, com as fontes lidas
   (grade vigente, nota da B3 de 07/11/2022 e o comunicado de que a Copa de 2022 não mudou horários, que ela indicou e
   eu conferi) e só compatibilidade por carimbo; o filtro de cobertura do pregão inteiro saiu (usava o resto do dia).
7. **LIMITE e inferência com decisões abertas** (meses, soma ÷ contagem, arredondamento do corte, cláusula sem número,
   família com três sempre). → tudo fixado no contrato comum.
8. **O carregador da Fila perde o contrato comum** (só guarda seis campos). → população, previsão e refutação de cada
   bloco carregam o essencial em uma linha e apontam para a cópia congelada.

## Pré-registro, rodada 2 — 2 must-fix (censura), aplicados como ela escreveu

- Lançar a censurada **no stop** podia **melhorar** uma perda já comprovada (abertura além do stop antes do buraco). →
  cenário de estresse = pior entre o stop e o preço mais adverso **observado**, declarado como cenário assumido, não
  limite.
- A resolução tinha de valer também para **metades, vizinhos e holdout**, cada um na sua população. → aplicado.

## Código, rodada 1 — 7 must-fix, todos corrigidos

1. Holm não punha p = 1 nas hipóteses em LIMITE. → limites antes da família.
2. O contrafactual da H-040 recalculava o stop de 0,5 % sobre a entrada do lado contrário (100 495 em vez de 100 500 no
   caso dela). → stop do lado da regra refletido na abertura bruta; teste com o caso dela.
3. O congelamento não fixava código nem configuração, e o holdout podia reler. → `infra/research/b3/freeze.py`:
   `config.txt` com réplicas, semente, limiares, custos, versões e sha256 do código e da cópia congelada; as fases
   recusam diferença, recusam rodar de novo, e o holdout recusa se não reproduzir byte a byte o relatório do primário.
4. Meses e metades usavam só operações com desfecho. → na emenda 1, "operação" = plano emitido (o vocabulário do
   funil congelado); ela **corrigiu a própria leitura** na rodada 2.
5. O `quantize(1e-10)` da razão de contração criava uma faixa de tolerância não registrada. → aritmética racional exata
   (`Fraction`).
6. Faltava a lista de exclusões por data e o funil por barra da H-040. → publicados.
7. "Sem dado" olha a disponibilidade até 16:30, depois das decisões, contra a frase "nenhuma exclusão usa dado
   posterior". **Não mudei a população congelada**: a emenda 1 declara que o item d prevalece e que é seleção por
   carimbo, nunca por preço, com a lista publicada.

## Código, rodada 2 — 1 must-fix

`--reps` livre deixava congelar com 20 réplicas (p mínimo 1/21, nenhuma passaria Holm). → só 10 000; menos exige
`--fixture-only` e o relatório sai rotulado "NÃO É A CONSULTA". Nice-to-have aceitos: a tolerância de empate é
puramente relativa (como a emenda diz) e o descritivo "bruto" diz de onde vem a saída.

## O que eu aprendi (vale para a próxima família)

- **O vocabulário do funil decide a estatística.** "Operação" antes de "sem barra na entrada" significa plano, e isso
  muda meses, metades e denominador da censura — escrever no pré-registro qual degrau cada número conta.
- **Censura por carimbo, não por desfecho**: um buraco depois de um stop também censura, senão a seleção depende do
  resultado; e o cenário de estresse nunca pode melhorar uma perda observada.
- **Congelar o código junto com os planos**: sem o sha256 do simulador e da configuração, "planos iguais" não impede
  rodar o primário com outra tarifa ou outra precedência.
- **Razão comparada com limiar se calcula exata** quando o limiar é número redondo e o dado é de grade (5 pts).

## Relacionado

[[Fila de Hipoteses]] · [[Mapa de Estrategias]] · [[EXP-0010-session-orb-faixa-de-abertura]] ·
[[KB-0082-reversao-de-15-minutos-o-sinal-e-o-fluxo]] · [[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]] ·
[[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] · [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]] ·
[[Revisoes-Astra/H-038-prereg|H-038-prereg]] · [[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]] ·
runbook `docs/runbooks/exportar-dados-mt5.md`
