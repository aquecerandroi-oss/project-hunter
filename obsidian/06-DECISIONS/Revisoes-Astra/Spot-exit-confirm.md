---
tags: [revisao-astra, spot-1, saida, stop, cotacao, execucao, risk-engine]
date: 2026-10-01
updated: 2026-10-01
status: registro
owner: risk-engine-guardian
decided_on: 2026-10-01
by: astra
tarefa: confirmar stop/alvo da spot/1 com uma segunda cotação (a executada) antes de vender, com prazo para o stop
veredito: desenho aceito com 3 must-fix e diff com 3 lacunas do episódio — todas absorvidas
---

# Revisão da Astra — stop/alvo da `spot/1` confirmados por uma segunda cotação

**Pedido:** desenho e diff da correção do achado 5 de [[KB-0172-perdas-da-spot-1]] (cotação fantasma: UNI 29/09 vendido
como "stop" com a marca −13,6 % e a Binance +0,39 %; NEAR 26/09 com alvo fantasma +3,6 % recusado na simulação).
Fontes brutas: `.claude/state/astra-review-spot-exit-confirm-design.md` e
`.claude/state/astra-review-spot-exit-confirm-diff.md`.

## Desenho — o que ela pediu e o que foi feito

1. **HIGH — a saída por tempo tem de sobreviver a qualquer resultado da confirmação** (o alvo vem antes do tempo na
   ordem; um alvo fantasma repetido mataria a saída por tempo). Feito: quando a confirmação não concorda ou falha,
   roda-se a regra sem preço (`emergency`/`sell_requested`/`time`) e, se valer, vende-se por ela, com a tolerância
   recalculada para o motivo final e sem a cotação de confirmação.
2. **MEDIUM — não gastar a tentativa antes da confirmação** (dois alvos descartados levariam a 3.ª venda à tolerância
   de pânico). Feito: a tentativa só é contada depois do plano aprovado; provado com dois alvos fantasmas seguidos de um
   real → tentativa 1, 50 bp.
3. **HIGH — três ticks em memória não são limite.** Feito: prazo explícito de 60 s desde o início do episódio,
   gravado na linha (`exit_intent.stop_unconfirmed_since`, sobrevive a reinício); cotação ilegível consome o prazo e
   não conta como recuperação; marca que falhou também não fecha o episódio; a troca stop↔alvo entre as duas cotações
   conta como episódio de stop nos dois sentidos; o relógio é relido depois do `await`.

**Mantido como estava, de propósito (concordância dela):** a Binance não é portão; a tolerância de pânico do stop
(300 bp desde a 1.ª tentativa) fica fora do escopo; alvo nunca é forçado; forçar o stop contra uma confirmação contrária
pode repetir o UNI depois do prazo — troca registrada entre dois riscos. A confirmação não garante preço nem fill: a
simulação continua sendo a última barreira.

## Diff — 3 lacunas no ciclo do episódio, corrigidas

Ela confirmou os dois primeiros must-fix do desenho como absorvidos e achou o terceiro **parcial**:

1. **HIGH — episódio vencido + marca que falha não chegava à venda** (sem marca, `decide_exit` não diz nada).
   Corrigido: `settle_stop_episode` devolve `stop` quando o episódio passou do prazo e a marca falhou;
   `plan_exit` então confirma ou força. Teste `test_an_overdue_stop_is_tried_even_when_the_mark_fails` (e o
   contrário: episódio novo + marca que falha continua esperando).
2. **HIGH — alvo com confirmação ilegível apagava o episódio de stop** (alternância alvo→stop / alvo→ilegível
   reiniciava o prazo sem fim). Corrigido: confirmação ilegível mantém o episódio; só cotação legível acima do stop o
   encerra. Teste sequencial t=0/20/40/60 → stop forçado em 60 s.
3. **MEDIUM — `set_exit_pending`/`clear_exit_pending` sobrescreviam `exit_intent`** e uma venda forçada que falhasse
   ganhava outros 60 s. Corrigido: os dois preservam a chave do episódio (SQL com `jsonb_strip_nulls`); teste no
   Postgres real, com mutação conferida (sem a preservação o teste falha).

**Nice-to-have:** confirmação distingue `quote_refused` (4xx) de `quote_failed` — feito. Cotação de confirmação
envelhecida entre a confirmação e o `swap` (duas escritas no banco) — **não feito**: sem medida de idade nem validade
máxima; a simulação continua sendo a barreira de execução, não do gatilho. `high_water_sol` pode guardar um pico
fantasma (o `GREATEST` não desfaz) — sem efeito nas saídas da spot hoje, registrado. **Concordou:** forçado recota na
perna (a cotação contrária não confirmou e pode ter outra tolerância); reaproveitar a cotação confirmadora; o `CASE`
JSONB do episódio.

## Revisão de código e do guardião (01/10)

- **Revisão de código (MEDIUM), corrigido:** episódio vencido + marca que falha + confirmação **legível** que não é
  stop forçava a venda — o `stop` injetado pelo prazo contava como evidência. Agora: confirmação legível acima da
  linha fecha o episódio sem venda; só força se a confirmação também for ilegível, e confirma se ela disser stop
  (teste do UNI em t=70 s com a marca em 429 e recotação normal: nada vendido, episódio fechado).
- **F2 (guardião), registrado:** na prática a tentativa forçada cai entre 60 e 80 s depois do início do episódio —
  o laço de marca roda a cada 20 s e o prazo só é lido na marca seguinte. Documentado no §19.2.
- **F3 (guardião), herdado, fora deste diff:** um alvo na tentativa ≥ 3 usa a tolerância de pânico (300 bp) e, com
  geometria apertada, poderia pousar abaixo da linha do stop. É mudança de política (`slippage_for`, desenho §4),
  não correção — fica para decisão do dono.

Ligações: [[KB-0172-perdas-da-spot-1]] · [[Perdas-spot-1]] · [[03-TRADING/Spot/README|Spot]] ·
[[06-DECISIONS/Revisoes-Astra/KB-0172-perdas-spot-1|KB-0172-perdas-spot-1]] ·
[[06-DECISIONS/Revisoes-Astra/Spot-ata-rent-fix|Spot-ata-rent-fix]]
