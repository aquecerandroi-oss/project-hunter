---
tags: [revisao-astra, spot-1, aluguel, contabilidade, execucao, risk-engine]
date: 2026-10-01
updated: 2026-10-01
status: registro
owner: risk-engine-guardian
decided_on: 2026-10-01
by: astra
tarefa: corrigir a constante de aluguel de ATA da spot/1 (ler da transação) e o script auditado que reprocessa as 4 posições
veredito: desenho aceito com 4 must-fix e diff com 3 must-fix reproduzidos — todos absorvidos
---

# Revisão da Astra — correção do aluguel de ATA da `spot/1`

**Pedido:** desenho (antes de implementar) e diff (antes de reportar) da correção do bug achado em
[[KB-0171-custo-real-da-spot-1]]: o executor descontava 2 039 280 lamports de aluguel quando a rede cobra 1 488 440.
Fontes brutas: `.claude/state/astra-review-spot-ata-rent-fix.md` (desenho) e
`.claude/state/astra-review-spot-ata-rent-fix-diff.md` (diff).

## Desenho — o que ela pediu e o que foi feito

1. **Script: quantidade histórica, não `spot_positions.tokens`** (o fechamento zera a coluna). Feito: o script confere
   o delta de token da transação contra `entry.filled_atoms` e recalcula o preço por átomo com ele; o risco inicial
   original é preservado.
2. **Fill legado na reabertura de órfão** podia trazer a constante de volta depois do deploy. Feito: todo fill novo
   grava `ata_rent_source = tx_meta_ata_balance`; um fill sem essa proveniência que diz ter travado aluguel vira
   **aluguel desconhecido** (`stored_fill_rent`), dobrado no gasto.
3. **Saldo retido ≠ financiamento pela carteira.** Feito: o aluguel só é lido se a conta criada for a **ATA da
   carteira para o mint** (endereço derivado e comparado); qualquer outra conta criada → `None`. O verificador
   (`spot_verify`) já só deixa criar ATA com a carteira pagando.
4. **Atomicidade do script.** Feito: linhas travadas `FOR UPDATE`, `UPDATE` com guarda sobre toda a contabilidade lida
   (`sol_spent`, `ata_rent`, `pnl_sol`, `r_multiple`) e `RETURNING` exigindo uma linha, tudo numa transação; qualquer
   recusa desfaz o lote inteiro (provado: uma posição ilegível no lote, e também uma falha depois de uma escrita já
   feita, deixam zero updates e zero auditorias).

**Respostas que mudaram o plano:** (a) delta líquido da conta nova, com prova de que é a ATA da carteira — sim;
pré-financiamento parcial conta só o complemento; delta zero (pré-financiamento integral) fica como desconhecido,
conservador. (b) dobrar o aluguel desconhecido no gasto — aceito, com a ressalva de que pode antecipar um stop (o
`r_now` usa o gasto): degradação conservadora, registrada. (c) teto da simulação não muda nesta correção (não derivar
a tolerância do próprio débito que ela limita). (d) `spot_orders.fill` histórico não é reescrito. (e) não precisa
reiniciar o executor: a refutação relê `closed_stats` a cada tique de entradas.

## Diff — 3 must-fix, todos reproduzidos por ela e corrigidos

1. **HIGH — derivar o endereço da ATA não prova quem pagou.** Ela reproduziu: terceiro deposita 1 488 440 na ATA da
   carteira na mesma transação → o extrator subtraía isso e inflava o PnL no aluguel inteiro. Corrigido: o aluguel só
   vale se um `system::createAccount` interno **com a carteira como origem** financiou exatamente aquele delta
   (`pumpfun.rent.rent_funded_by`, o leitor que já existia); endereço pré-financiado (transferência, sem
   `createAccount`) ou depósito de terceiro → desconhecido, incorporado ao gasto. Testes:
   `test_a_deposit_funded_by_someone_else_is_never_subtracted`, `..._pre_funded_..._is_unknown`,
   `..._create_account_that_disagrees_with_the_balance_is_unknown`.
2. **MEDIUM — outra conta do mesmo mint escondia a ATA nova** (`ata_created = visto depois e não antes`): aluguel 0
   sem marca. Corrigido: criação decidida **por `accountIndex`**; teste `..._another_account_of_the_same_mint_...`.
3. **MEDIUM — "already correct" ignorava os campos em `entry`/`params`** que o próprio script escreve. Corrigido:
   `Fix.changed` compara colunas **e** `entry.sol_spent_lamports`, `entry.ata_rent_lamports`,
   `params.ata_rent_lamports`, `params.entry_sol_per_atom`; teste parametrizado com cada campo velho.

**Nice-to-have absorvidos:** índice não inteiro (`[]`) e saldo fracionário não derrubam nem truncam (viram
desconhecido); cruzamento com o `fill` da ordem de entrada (`fill_mismatch`); teste de rollback **depois** de uma
escrita; "dobrado" → "incorporado" no contrato; reserva (aperta) separada da tolerância da simulação (afrouxa) na doc.
**Não feito:** aceitar delta zero com prova de inicialização sem aporte (fica desconhecido, conservador). **Concordou:**
ALT e `jsonParsed`, guarda do `UPDATE` com o `Decimal` lido, tolerância de R (erro máximo 5e-11 < 1e-9), runbook
PowerShell/SSH (o `ops` usa a imagem implantada e o `obsidian/` montado só-leitura).

## Revisão do guardião (01/10) — F1, corrigido

**F1 (HIGH pela Astra):** o `SELECT ... FOR UPDATE OF p` dos candidatos não filtrava `status = 'closed'` — uma posição
**aberta** ficava travada durante as chamadas `getTransaction` (até no ensaio), bloqueando o `set_mark`/a saída do
executor. Corrigido: só as fechadas são travadas; as abertas são listadas por um `SELECT` separado, sem trava (teste
com `FOR UPDATE NOWAIT` de uma segunda conexão: aberta livre, fechada travada). Da revisão de código: falha da RPC e
coluna nula viram recusa nomeada (`rpc_failed`, `position_not_closable`, saída 65); `TxFill.ata_created` (sem leitor)
saiu; o script foi dividido (`spot_fix_ata_rent_rules.py`, parte pura) para caber em 350 linhas.

Ligações: [[KB-0171-custo-real-da-spot-1]] · [[KB-0172-perdas-da-spot-1]] · [[03-TRADING/Spot/README|Spot]] ·
[[06-DECISIONS/Revisoes-Astra/KB-0171-custo-spot1|KB-0171-custo-spot1]] ·
[[06-DECISIONS/Revisoes-Astra/Spot-exit-confirm|Spot-exit-confirm]]
