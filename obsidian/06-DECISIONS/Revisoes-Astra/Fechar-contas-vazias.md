---
tags: [astra, revisao, carteira, risco, meme-executor, ops]
date: 2026-09-28
updated: 2026-09-28
status: registro
owner: risk-engine-guardian
decided_on: 2026-09-28
by: Astra + risk-engine-guardian
---

# Revisão da Astra — fechar as contas de token vazias da carteira (28/09/2026)

**Tarefa:** pedido do Everton. A ferramenta auditada `close_empty_token_accounts` devolve à carteira do robô (`ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4`) o aluguel das contas de token vazias. Pela leitura do guardião de 28/09 às 06:17Z, são 80 contas e cerca de 0,1210 SOL. O dry run é o padrão, e só o Everton roda o `--apply`, na VPS. O código fica em `infra/scripts/close_empty_token_accounts.py`, com os módulos `_rules.py` e `_reads.py`. O passo a passo para o Everton está em `infra/vps/README.md`, na seção "Recuperar o aluguel das contas de token vazias".

**Fechar a conta só devolve o aluguel.** Nenhum token é movido, e a conta congelada do golpe (`DgY9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg`) nunca entra num lote. Desde a rodada de segurança (abaixo), o mint dela está numa lista fixa e sai sempre como `skipped:never_touch:phishing`, qualquer que seja o estado da conta. Antes disso, só o congelamento a mantinha fora. A exceção por mint de [[2026-09-28-excecao-auditada-token-golpe]] continua sendo o único remédio para a checagem de [[Wallet-unrecognized-holdings]]. Recuperar aluguel não resolve o golpe.

**Reuso, não reescrita.** O caminho de envio é o da T4.77/T4.77b ([[T4.77-close-atas-token2022]]): veredito por conta, lotes de 8 num programa só, verificador puro (só `CloseAccount` com destino e autoridade iguais à carteira), simulação com invariante, assinatura gravada antes do envio e recuperado lido do meta da transação. Os mints reconhecidos saem do SQL do próprio executor (`wallet_holdings.recognized_mints`). O que esta ferramenta põe por cima:
- ficam fora a ATA de WSOL, a de USDC e todo mint reconhecido;
- recusa com nome quando há compra em voo, `EMERGENCY` ou falha de leitura;
- a carteira é relida antes de cada lote (TOCTOU);
- o portão `--note`;
- linhas em `audit_logs`.

## Rodada de desenho (antes do código)

Parecer: **favorável, com três MEDIUM**, todos aceitos e com teste.
1. **Resposta da RPC sem lista era lida como "sem contas".** `{"value": {}}` num dos programas virava inventário parcial. Agora é `chain_read_failed`.
2. **A proveniência precisava ser gravada antes do envio.** Se o processo morresse depois do broadcast, a nota e o ator se perdiam. Agora uma linha `…intent` em `audit_logs` (id da execução, lote, contas, sha256 da nota) é commitada antes de cada lote, e o id da execução vai também no `reason` do `system_events` que carrega a assinatura.
3. **Parar quando o lote confirma mas recupera menos que o esperado.** O `run_batch` devolvia `confirmed` e a execução seguia. Agora ela para com `stopped:recovered_below_expected`.

**Kill switch: só `EMERGENCY` recusa.** Estado ilegível também recusa, porque o leitor já converte Redis morto ou linha ausente em `EMERGENCY`. Fechar conta vazia não é entrada, e com `TRADING_DISABLED` é quando é mais seguro. O `meme_close_atas.py` exige `ACTIVE`; aqui a regra foi afrouxada de propósito.

**A corrida que sobra, sem perda de principal** (tabela da Astra):
- se a compra do executor vem primeiro, o fechamento falha e só a taxa se perde;
- se o fechamento vem primeiro e a compra recria a ATA, o aluguel volta a ficar preso;
- se o fechamento vem primeiro e a compra conta com a ATA existente (`creates_ata` falso), a compra falha e a oportunidade se perde.

A checagem de compras em voo, repetida a cada lote, diminui a janela, mas não é exclusão mútua. Por isso a recomendação é rodar com a `spot/1` sem posição e, de preferência, com as entradas desligadas.

**Aceitos também, da lista de nice-to-have:** a janela de graça de 60 s conta a partir do instante **anterior** à leitura da cadeia; um lote inteiro descartado é pulado sem envio; a validação do destino é uma recusa explícita, não um `assert`.

## Rodada do diff

Parecer: **REQUEST_CHANGES**, com quatro achados.

**Aceitos, cada um com teste:**
1. **Falha de leitura sem recusa com nome.**
   - Um `getBalance` ilegível deixava o dry run terminar com código 0, e o passo 4 do runbook depende desse saldo. Agora o dry run imprime a lista e sai com 65 (`balance_unreadable`).
   - Um timeout de `get_latest_blockhash` ou do saldo dentro do `run_batch` virava um crash que dizia "talvez enviado". Agora um `SignTracker` registra se houve pedido de assinatura. Exceção antes da assinatura vira `batch_unsent:<tipo>`, código 65, porque nada saiu. Exceção depois dela mantém o caminho `crashed_mid_batch` com o número do lote. A exceção do `run_batch` nunca é convertida em recusa depois da assinatura.
2. **Dois applies no mesmo bloco.** Colados juntos, o segundo rodava mesmo depois de um 66. O passo 3 agora tem dois blocos (3a e 3b) e uma conferência obrigatória entre eles.
3. **Arquivo de teste com 363 linhas.** O portão de tamanho não olha `tests/`. Os dublês foram para `close_empty_token_accounts_rig.py`.
4. **Nice-to-haves.** O teste agora prova que a linha de intenção é commitada antes do envio, e não só inserida (`audit:intent → commit → run_batch`). O runbook deixou de dizer que "todas as linhas levam o sha256 da nota": uma recusa anterior ao portão fica registrada sem nota.

**Já estava resolvido quando ela leu:** "a nota do runbook não existe". Esta nota foi criada logo depois da leitura dela, e o portão foi conferido contra o arquivo real (`require_note` → ok; o sha256 muda a cada edição da nota e fica gravado em cada linha de `audit_logs`).

**Pontos em que ela concordou:** nenhum caminho do dry run assina, envia ou grava dado de negócio; a ordem do `_apply` está certa (preflight → plano → nada a fechar sai → nota → chave e igualdade → reconferência por lote → intenção persistida → envio); as aspas do runbook funcionam no PowerShell 5.1. Ela conferiu isso ao vivo: `parse_errors=0`, sem `$` e sem aspas duplas.

**Rejeitado, com motivo:** acrescentar o procedimento ao [[KB-0149-o-que-a-mesa-real-ensinou]]. A regra daquela nota é que só entra o que foi medido com dinheiro real, e nada foi aplicado ainda. O valor recuperado entra lá depois do `--apply` do Everton, lido do `lamports_recovered`.

Brutos: `.claude/state/astra-review-close-empty-token-accounts-design.md` e `…-diff.md`.

## Rodada de segurança (security-reviewer + Astra, 28/09)

Parecer: **aprovado com correções.** Nenhum dos dois achou caminho que mande o aluguel para terceiros ou que assine algo além de ComputeBudget e `CloseAccount`. Foram três achados, todos corrigidos com teste. Bruto: `.claude/state/astra-review-review-close-empty-accounts-sec.md`.

**Divergência de gravidade, registrada:** a Astra deu MEDIUM aos três. O security-reviewer deu MEDIUM ao 1 e LOW ao 2 e ao 3: nenhum dos dois move dinheiro, só afeta a auditoria e a leitura do código de saída. As correções foram feitas do mesmo jeito, porque eram baratas e cada uma tinha um cenário concreto.

1. **MEDIUM (os dois) — a conta do golpe ficava de fora só pelo estado on-chain, que muda.**
   - **O problema:** se o emissor descongelar a conta e o *permanent delegate* dele queimar o saldo, ela passa a ler "inicializada, saldo 0, só `immutableOwner`, é ATA", e o classificador da T4.77b diz `close`. O teste agora mostra esse furo antes de mostrar a correção. O *permanent delegate* é extensão do **mint**; não aparece como `delegate` da conta.
   - **O que foi feito:** a lista fixa `NEVER_TOUCH_MINTS` (começa com `DgY9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg`) é conferida no `judge()` antes de qualquer outro veredito e de novo no `refresh_batch`, com o rótulo `skipped:never_touch:phishing` / `dropped:never_touch:phishing`.
   - **Testes:** a conta descongelada, zerada e só com `immutableOwner` fica de fora; a linha que chega a um lote cai na releitura; uma conta congelada de outro mint continua saindo como `skipped:frozen`.
   - **Consequência:** a lista mora no código, não no Postgres. É outra coisa que a exceção de [[2026-09-28-excecao-auditada-token-golpe]]: aquela só tira o mint da lista de "estranhos"; esta impede qualquer instrução sobre ele.
2. **LOW (revisor) / MEDIUM (Astra) — depois de um INSERT com erro, a linha `.run` também falhava.** O INSERT com erro deixa a transação abortada, e o `finally` gravava na mesma sessão sem rollback. O revisor reproduziu `InFailedSQLTransactionError` no PG16.
   - **O que foi feito:** um `rollback_quietly` antes da linha `.run`. Ele não descarta nada, porque cada linha anterior foi commitada sozinha.
   - **Testes:** o dublê de sessão agora imita a transação abortada (tudo falha até o `rollback()`). O teste morre com o mutante que tira o rollback. Um teste de integração no PostgreSQL 16 mostra os dois lados: sem rollback, a linha `.run` falha com transação abortada; com rollback, ela entra.
3. **LOW (revisor) / MEDIUM (Astra) — o código 65 também saía depois de um lote assinado e confirmado.** Isso acontecia em `audit_unwritten` com `confirmed` e em `recovered_below_expected`. Quem lesse 65 como "nada assinado" podia rodar de novo sem reconciliar.
   - **O que foi feito:** código novo, **68 = lote assinado e confirmado, depois parou**. O 65 passou a valer só para "nada assinado no lote corrente". Corrigidos a docstring e o teste que fixava o 65.
   - **Runbook:** manda reconciliar a assinatura com 66, 67, 68 ou `crashed_mid_batch`, e avisa que a Solscan mostra duas instruções do ComputeBudget (`SetComputeUnitLimit`, `SetComputeUnitPrice`) antes dos `CloseAccount`.

**Nice-to-have aceito:** a docstring deixou de dizer "idêntica byte a byte". A releitura compara os campos de `TokenAccountRow`, não os bytes da conta nem o slot.

**Fora desta tarefa:** o `JSONDecodeError.doc` do `_parse_secret` pode guardar o texto da chave dentro do objeto da exceção. Isso não aparece no traceback impresso e não é código desta ferramenta: é do `hunter_core` (signer), que fica para o dono do signer.

## Relacionado

[[Wallet-unrecognized-holdings]] · [[2026-09-28-excecao-auditada-token-golpe]] · [[T4.77-close-atas-token2022]] · [[KB-0149-o-que-a-mesa-real-ensinou]] (o aluguel foi 33 % do prejuízo da mesa) · [[KB-0165-staking-do-sol-parado]] · [[Open Bugs]] · [[2026-09-28]] · [[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
