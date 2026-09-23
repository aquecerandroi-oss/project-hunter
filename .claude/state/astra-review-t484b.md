**RESUMO**

**REQUEST_CHANGES — resta um must-fix HIGH**, preexistente e não apontado na primeira rodada. Revisão como `code-reviewer`.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executei testes nesta rodada; os 747 testes e as mutações são resultados reportados por você.

**MUST-FIX**

**(a) Ainda existe `failed` sem certeza:** o reconcile completa respostas curtas com `None` em [treasury_reconcile.py:66](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_reconcile.py:66), e `None` com idade superior a 180 segundos vira `failed` em [treasury_rules.py:184](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_rules.py:184).

**Cenário:** a troca confirmou, mas o meta estava indisponível; ficou `submitted`. Aos 200 segundos, uma resposta incompleta retorna `[]`. O preenchimento artificial produz `None` e a linha vira `failed`, sem consultar seu meta. Ela desaparece tanto do teto de USDC quanto do influxo de SOL, conforme [treasury_db.py:45](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_db.py:45).

**Correção:** resposta incompleta deve manter pendência. Além disso, idade de relógio mais ausência de status não deve provar “nunca pousou”: a expiração precisa considerar a validade efetiva do blockhash e a reconciliação da assinatura. A [documentação oficial](https://solana.com/developers/cookbook/transactions/confirmation) descreve a verificação por altura de bloco.

**NICE-TO-HAVE**

Manter a pendência de observabilidade no heartbeat; registrar o motivo apenas no log é uma redução explícita de escopo aceitável, conforme [treasury_reconcile.py:76](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_reconcile.py:76).

**O QUE EU FARIA DIFERENTE**

**(c) Antes de ligar, exigiria testes de:**

- Status confirmado + meta indisponível → resposta curta/ausente após 180 segundos → continuar pendente → liquidar quando o meta aparecer.
- Falha no commit de `mark_submitted` → nenhum broadcast; a fronteira está em [treasury_send.py:221](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_send.py:221).
- Envio aceito com resposta perdida → reinício → duas reconciliações → uma liquidação, nenhum reenvio.

**CONCORDO COM**

- O HIGH anterior do fill foi corrigido: ambos usam `landed_sol_fill`, recusando delta não positivo. Não encontrei outro erro concreto de fill nesse caminho: [treasury_send.py:263](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_send.py:263), [treasury_reconcile.py:119](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_reconcile.py:119).
- **(b) Não identifiquei ciclo de import:** `treasury_send` importa o helper; `treasury_reconcile` não importa o envio, e `ExecutorContext` fica sob `TYPE_CHECKING`: [treasury_reconcile.py:26](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_reconcile.py:26).

**OBSIDIAN**

- **KB-0130 — Tesouraria USDC→SOL:** registrar as correções e o bloqueio restante na classificação de expiração.
- **Revisões-Astra / T4.84:** registrar esta segunda rodada e os testes exigidos antes da ativação.