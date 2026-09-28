---
tags: [revisao-astra, cripto, fibonacci, lta, resultado, h-025, h-026]
date: 2026-09-28
updated: 2026-09-28
status: registro
owner: sexta-feira
decided_on: 2026-09-28
by: astra
tarefa: R85 — resultado e código da H-025 (Fibonacci 50–61,8 % no diário) e da H-026 (LTA diária, A e B)
veredito: concorda com H-025 NÃO CONFIRMA (primária e estrutural), H-026 A REFUTA e H-026 B NÃO CONFIRMA; 4 must-fix de código aceitos e corrigidos, rótulos inalterados
---

# Revisão da Astra — resultado da H-025 e da H-026 (R85)

**Pedido:** conferir o código (`.claude/state/r85/`), a saída real, a contagem prévia e a fumaça contra o
pré-registro e a emenda; dizer se os vereditos seguem a letra; leitura honesta de A (IC inteiro abaixo de zero) e de B
(D ≥ MRE com IC cruzando zero). Ela rodou os 22 testes que existiam então, reproduziu contagens e D, e recalculou em memória.

**Vereditos:** os quatro corretos pela letra — H-025 primária e estrutural `NÃO CONFIRMA`; A `REFUTA` o tamanho
previsto (+1 p.p.); B `NÃO CONFIRMA` (IC cruza zero, Holm 0,22).

**Quatro must-fix de código, aceitos; cada um ganhou teste que falhou antes e passa depois:**

1. **A LTA vivia até b + 181.** O registro diz "morre 180 velas depois de b"; o código usava `>`. Cenário dela: 3.º toque
   exatamente em b + 180 emitia A. → `>=`. **Mudou os números da H-026 sem mudar rótulo:** A −1,079 → **−1,085**
   [−2,079; −0,021]; B +1,060 → **+1,089** [−0,755; +2,891], Holm 0,237 → 0,223 — iguais aos que ela recalculou.
2. **A mínima da vela podia passar à frente de uma saída já decidida na abertura** (abre em 140 acima do alvo 130 e cai
   a 90: o código saía no stop). → a abertura além do stop ou do alvo decide primeiro. Nenhuma operação deste painel
   afetada (ela conferiu).
3. **K6 bloqueava só o CONFIRMA**, não o REFUTA. → K6 depois do limite de dado e antes dos demais rótulos. Sem impacto
   (maior concentração 5,9 % em A e 7,1 % em B).
4. **A estrutural dependia de a saída fixa de 10 d existir.** → a estrutural fica; só o descritivo pareado exige as
   duas. Sem impacto (0 censuras).

**Nice-to-have aceitos:** as sensibilidades estruturais de 60 e 180 d registradas na emenda e a contagem de réplicas
descartadas, que faltavam no relatório — agora impressas (IC 60 d [−3,375; +3,821], 180 d [−2,926; +3,544]; 0
réplicas descartadas). **Registrado sem mudar código:** o controle da LTA exclui qualquer vela **perto** de uma linha
viva, mesmo quando isso não é um toque contado (proximidade geométrica ≠ toque distinto) — dito na KB-0169.

**Leituras que ela pediu e que ficaram escritas:** em A, "efeito oposto" é descritivo (o Holm testou superioridade);
o controle de A (LTA confirmada longe da linha) é compatível com **momentum transversal** — não concluir que a LTA
causa perda, que vender o toque paga, nem que B acrescenta algo a um rompimento qualquer; B é **pista descritiva**,
não um quarto veredito, e não autoriza trocar H = 10 por H = 20 depois de ver. Otimista = pessimista é plausível: uma
única operação (LUNA, 06/05/2022, em A) terminou em fim de série, diferença invisível em 3 casas.

Nada rejeitado.

**Bruto:** `.claude/state/astra-review-H-025-result.md` · `.claude/state/r85/astra_result.log` ·
`.claude/state/r85/h025_h026.txt` (final) · `.claude/state/r85/h025_h026_v1_antes_da_revisao.txt` (antes)
**Relacionado:** [[KB-0169-fibonacci-e-lta-diaria-no-dado|KB-0169]] · [[KB-0168-fibonacci-elliott-e-lta-diaria|KB-0168]] ·
[[H-025-H-026-prereg]] · [[Fila de Hipoteses]]
