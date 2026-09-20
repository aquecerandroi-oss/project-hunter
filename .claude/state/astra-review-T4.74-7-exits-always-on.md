**RESUMO**

A1 está corrigido no laço automático: `main.py:320` cria a tarefa independentemente de `SPOT1_ENABLED`, conforme `spot_exits.py:86`. A2 distingue corretamente recusas duras e transitórias. Porém, o fechamento manual tem bloqueadores.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão somente leitura, como `risk-engine-guardian`.

**TESTES**

Não executei testes nesta revisão; as conclusões abaixo são de inspeção estática. Li os testes novos e os de fechamento manual. Não afirmo aprovação da suíte.

**MUST-FIX**

1. [infra/scripts/spot_desk_markets_close.py:79](/C:/dev/project-hunter/infra/scripts/spot_desk_markets_close.py:79) — **ALTA — O INSERT omite o `id` obrigatório.** O DDL declara `id uuid NOT NULL`, sem default ([spot_desk.py:112](/C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:112)). **Cenário:** uma venda manual válida passa por todas as guardas; `--apply` falha por violação de NOT NULL, e a posição vendida continua aberta no banco. O fake aceita o INSERT sem validar esse contrato ([test_spot_desk_close_manual.py:140](/C:/dev/project-hunter/infra/scripts/tests/test_spot_desk_close_manual.py:140)). Gerar e fornecer o UUID explicitamente.

2. [infra/scripts/spot_desk_markets_close.py:150](/C:/dev/project-hunter/infra/scripts/spot_desk_markets_close.py:150) — **ALTA — A carteira informada não é vinculada à compra da posição.** A consulta da posição não busca a identidade da carteira nem a assinatura de entrada (`:68`); a validação comprova somente que a transação pertence ao `--wallet` informado. **Cenário:** o operador informa a carteira pessoal e sua venda do mesmo mint e quantidade, posterior à entrada do robô. A validação aceita essa venda para quitar uma posição cujos tokens continuam na carteira do robô, retirando sua proteção e atribuindo PnL alheio. Conferir a carteira contra evidência confiável da entrada.

3. [infra/scripts/spot_desk_markets_close.py:212](/C:/dev/project-hunter/infra/scripts/spot_desk_markets_close.py:212) — **ALTA — “Sem venda em voo” não é uma guarda atômica.** O SELECT não bloqueia a linha (`:68`), e o fechamento verifica apenas `status='open'` (`:91`). O executor também ignora o retorno de `set_exit_pending` ([spot_exits.py:258](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:258)). **Cenário, após corrigir o INSERT:** o executor já carregou a posição; o script registra sua venda externa e fecha a linha; o executor tenta marcar a saída, recebe `False` e mesmo assim chama `spot_leg`. Havendo outro saldo do mesmo mint na carteira, vende novamente a quantidade da posição encerrada. É necessária exclusão mútua entre processos e aquisição condicional da posição, cujo fracasso impeça o envio.

4. [infra/scripts/spot_desk_markets.py:310](/C:/dev/project-hunter/infra/scripts/spot_desk_markets.py:310) — **MÉDIA — A captura de `Refused` dentro de `conn.begin()` permite commit parcial.** **Cenário, após corrigir o INSERT:** outra execução fecha a posição entre a leitura e o UPDATE; o script já inseriu a ordem confirmada, mas o UPDATE não retorna linha e lança `Refused` ([spot_desk_markets_close.py:295](/C:/dev/project-hunter/infra/scripts/spot_desk_markets_close.py:295)). O chamador captura e retorna normalmente, permitindo commit da ordem sem o fechamento correspondente nem o evento. Capturar a recusa fora do contexto transacional ou fazer rollback explícito.

**NICE-TO-HAVE**

[spot_stats.py:59](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_stats.py:59) — **BAIXA — Reinícios podem ocultar uma indisponibilidade persistente.** Com reinícios antes de completar 30 recusas, `stuck_exits` nunca aparece, embora a posição continue sem saída. Aceito a contagem em memória como alerta operacional auxiliar, não como garantia durável. O orçamento de falhas duras é recuperado do banco ([spot_exits.py:203](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:203)).

**O QUE EU FARIA DIFERENTE**

Acrescentaria testes com PostgreSQL real para o fechamento manual: INSERT completo, concorrência com o executor e rollback após inserção. Incluiria também carteira incompatível com a entrada.

**CONCORDO COM**

- A flag deve bloquear apenas entradas. A alteração não introduz outro caminho de assinatura; a releitura do kill switch permanece antes dela ([spot_send.py:210](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:210)).
- Uma saída `submitted_unconfirmed` permanece sob reconcile, sem nova tentativa naquele fluxo ([spot_exits.py:299](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:299)).
- A distinção por `retryable` está correta; inclusive HTTP 429 continua transitório no cliente Jupiter ([client.py:156](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/jupiter/client.py:156)).

**OBSIDIAN**

- **Spot — a mesa `spot/1`** — documentar saídas independentes da flag, limite do alerta em memória e bloqueadores do fechamento manual.
- **Revisoes-Astra/Index** — vincular esta revisão de T4.74-7 e suas condições de aceite.

**REPROVADO**