---
tags: [revisao-astra, cripto, lta, pre-registro, coorte-prospectiva, h-026, h-028]
date: 2026-10-01
updated: 2026-10-01
status: registro
owner: quant-engineer
decided_on: 2026-10-01
by: astra
tarefa: desenho e instrumento da coorte prospectiva do B da H-026 (rascunho da H-028 em `.claude/state/h026b-forward/PREREG.md`), antes de qualquer detecção de dia ≥ 2026-09-28 e de qualquer retorno
veredito: "três rodadas; 6 + 4 + 2 must-fix aceitos, cada um com teste que falhou antes; nada rejeitado; contraste P trocado para gatilho comum; congelado em 01/10 03:33Z"
---

# Revisão da Astra — pré-registro da coorte prospectiva do B (H-028, rascunho)

**Pedido:** ler o rascunho do pré-registro e o detector diário (`detect_daily.py`, `brk.py`, testes, contagem cega)
contra a [[KB-0169-fibonacci-e-lta-diaria-no-dado|KB-0169]] (parte D: coorte prospectiva com H = 10 d, contraste contra
rompimento sem LTA, custo real da `spot/1`), o bloco H-026 da [[Fila de Hipoteses]] e a revisão
[[H-025-H-026-resultado]]. Nenhum evento da coorte detectado e nenhum retorno lido antes das três rodadas.

## Rodada 1 — 6 must-fix, todos aceitos

1. **O comparador comparava estratégias, não a linha.** O B rompe a máxima entre toques; o "rompimento simples" rompe o
   último pivô de alta confirmado — só 181 dos 336 B são também rompimento simples. → **contraste P de gatilho comum**:
   B ∩ rompimento simples × rompimento simples **sem toque A nas 21 velas reais** (a janela que arma um B), no mesmo dia;
   leitura restrita a "associação incremental do filtro B", não mecanismo. Recontagem cega refeita.
2. **REFUTA sem suporte mínimo e K6 depois do rótulo.** → K6 primeiro; < 30 eventos ou < 15 intervalos de 28 d com
   evento → `LIMITE DE DADO` para qualquer rótulo, inclusive REFUTA.
3. **Parada e poder não batiam com as populações de cada contraste.** → análise única na parada dura (2030-09-27),
   pisos e poder por contraste; o texto diz que P não deve alcançar o piso.
4. **Insumos não preservados** (rebaixar tudo a cada dia perde as velas de moeda deslistada; revisão de máxima antiga
   passa despercebida; qualquer HTTP 400 virava "símbolo desconhecido"). → arquivo por primeira observação
   (`klines_fwd.csv`), revisões à parte, só o código −1121 conta.
5. **Identidade `SYM` × `SYM#0`** muda quando uma lacuna posterior parte a série. → (símbolo da série, início do
   segmento, símbolo negociado).
6. **Idempotência só sequencial; hash do texto gravado mas não conferido.** → trava `O_EXCL`, última linha inválida
   recusada, `frozen.json`.

Também aceitos: margem 00:10Z testada na borda; concentração das comparações publicada; a abertura de d + 1 é preço de
referência (sensibilidade descritiva às 01:00Z); dias reconstruídos marcados.

## Rodada 2 — 4 must-fix, todos aceitos

Vela faltando virava falta de evento → **política de cobertura** (o dia espera); linha de CSV truncada podia virar
"primeira observação" → **validação** linha a linha; o manifesto congelava só o texto → **congela também código e
artefato do R84**, e a classificação de bases novas **só cresce**; a parada dura não estava no detector → **aplicada**.
Ela concordou com a janela de 21 velas reais e com `groups_of`.

## Rodada 3 — 2 must-fix, aceitos

Acrescentar a mesma base com outro rótulo trocava a classificação → **uma classificação por base**; ausência dispensada
por status não ficava registrada → **cada dispensa grava símbolo, dia e status observado**.

## O que fica escrito (dela e meu)

- **P não deve confirmar nesta coorte:** pela contagem cega no painel do R85 ([[KB-0169-fibonacci-e-lta-diaria-no-dado|KB-0169]]),
  P teve **90 eventos em 7,56 anos (11,9/ano)** e R **323 (42,7/ano)**; até 2030-09-27 esperam-se ~48 em P (piso 150)
  e ~171 em R (poder ≈ 65 % para +3 p.p.). O desfecho esperado é `LIMITE DE DADO`. Ela preferia, antes, um teste
  retrospectivo pré-registrado do contraste incremental; com o gatilho comum ele também teria só 90 eventos — abaixo
  do mesmo piso. Decisão do orquestrador (não minha): rodar a coorte como arquivo barato, rodar o retrospectivo, ampliar
  o universo numa hipótese nova, ou parar aqui.
- **Custos:** trocados pelos medidos na [[KB-0171-custo-real-da-spot-1]] (0,2465 %/perna; estresse 0,335 %); taxa fixa
  convertida em percentual é aproximação declarada; o aluguel da conta de token é depósito, publicado à parte.
- **Congelamento substituído uma vez:** o primeiro `frozen.json` (03:31Z) foi trocado às 03:33Z porque a primeira
  corrida real caiu na busca (par USDT com nome em caracteres CJK na URL), **antes de qualquer detecção** e sem nada
  gravado; correção com teste; texto do pré-registro inalterado (mesmo sha256). Registro em
  `frozen_v0_superseded.reason.txt`.

Nada rejeitado.

**Bruto:** `.claude/state/astra-review-H-026B-forward.md` · `-round2.md` · `-round3.md` · instrumento e saídas em
`.claude/state/h026b-forward/`
**Relacionado:** [[KB-0169-fibonacci-e-lta-diaria-no-dado|KB-0169]] · [[KB-0171-custo-real-da-spot-1]] · · [[Proximas Hipoteses]] (decisão de 01/10: coorte arquivada)
[[H-025-H-026-prereg]] · [[H-025-H-026-resultado]] · [[Fila de Hipoteses]] · [[EXP-0016-trendline-breakout]]
