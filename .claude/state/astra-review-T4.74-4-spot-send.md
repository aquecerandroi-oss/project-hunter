**RESUMO**

**DONE_WITH_CONCERNS — recomendo corrigir dois achados antes de liberar o caminho real.** A assinatura persistida antes do envio e o tratamento de envio ambíguo estão corretos. Os problemas reproduzidos são a janela do kill switch e a atribuição dos saldos à operação.

Revisão como `risk-engine-guardian`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit.

**TESTES**

Executei com bytecode e cache do pytest desabilitados, sem sincronização de dependências:

```text
uv run pytest services/meme-executor/tests/test_spot_money_path.py services/meme-executor/tests/test_spot_entries.py services/meme-executor/tests/test_spot_exit_rules.py -q -p no:cacheprovider

72 passed in 1.31s
```

Também executei reproduções em memória, via `uv run python -`, usando os fakes existentes. Saída relevante:

```text
kill_changes_during_simulation: confirmed signs= 1 refreshes= 1
sol_read_stale statuses= ['simulated', 'submitted', 'confirmed'] spent= 50000000 source= ticket_fallback
inflow_0_04_sol statuses= ['simulated', 'submitted', 'confirmed'] spent= 10060720 source= chain_delta
```

São cenários sintéticos; não houve envio real.

**MUST-FIX**

1. [spot_send.py:164](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:164) — **ALTA — a última releitura do kill switch acontece antes das leituras de saldo, da simulação e da transação de banco.** A assinatura ocorre em [spot_send.py:201](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:201), sem nova checagem. **Cenário:** o interruptor muda para `TRADING_DISABLED` enquanto a simulação aguarda o RPC; quando ela termina, a compra ainda é assinada e enviada. Reproduzido. A implementação satisfaz literalmente “entre admissão e assinatura”, mas deixa uma janela de I/O evitável. Recomendo reler após a simulação/invariante, preservando a passagem das vendas. A recusa nessa etapa precisa considerar que `mark_refused` atualmente só aceita linha `admitted` ([spot_repo.py:150](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo.py:150)).

2. [spot_send.py:235](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:235) e [spot_entry_writes.py:86](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entry_writes.py:86) — **ALTA — deltas da carteira inteira são tratados como fill da transação; inconsistência ainda pode virar gasto estimado confirmado.** **Cenário reproduzido:** compra com gasto líquido de rent de **50.060.720 lamports**, enquanto entram **40.000.000 lamports** na carteira, grava gasto de **10.060.720**, com fonte `chain_delta`. Isso infla o resultado em aproximadamente **53,33 R**, para R unitário de 750.000 lamports, e pode disparar alvo falso: a regra calcula R usando esse gasto ([spot_exit_rules.py:67](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:67)). Outro cenário reproduzido: leitura SOL atrasada, mas token atualizado, confirma com delta SOL zero e substitui o gasto pela ficha, omitindo taxas. Recomendo preencher pelos metadados da **assinatura específica**; enquanto ilegíveis, manter pendente. O RPC já oferece `get_transaction` ([tx_rpc.py:184](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx_rpc.py:184)).

**NICE-TO-HAVE**

- [spot_entries.py:168](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entries.py:168) — **BAIXA, operacional — usar o teto de prioridade torna a seleção muito restritiva, mas está conforme o desenho.** Pela fórmula de [spot_profile.py:238](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/spot_profile.py:238), ficha de 0,05 SOL, stop de 1,5% e prioridade de 100.000 produzem:
  
  | Impacto por perna | Custo estimado |
  |---|---:|
  | 0% | 0,48 R |
  | 0,015% | 0,50 R |
  | 0,06% | 0,56 R — recusa |

  **Cenário:** sinal economicamente aceitável com prioridade efetiva baixa é recusado porque a admissão provisiona o teto. É um problema real de frequência e seleção da amostra, não um bypass de risco. Stops inferiores a **1,44%** já não passam nem com impacto zero, nesses parâmetros. Não mudaria limites automaticamente.

**O QUE EU FARIA DIFERENTE**

A franquia de [spot_send_rules.py:76](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:76) é **conservadora e frouxa quanto ao rent**, não evidentemente apertada: conta instruções ATA, inclusive criação idempotente de conta existente e WSOL fechado na mesma transação.

Com uma criação e prioridade de 100.000, tolera **2.154.280 lamports**; reproduzi o check de venda aceitando delta SOL zero para mínimo de 2.000.000. Isso demonstra a fraqueza do invariante isolado, **não prova uma transação explorável que atravesse também o verificador**; portanto, não elevo a must-fix.

Eu separaria rent efetivamente retido de rent transitório/reembolsado. Os 10.000 adicionais não são o principal excesso.

**CONCORDO COM**

- **Verificação e simulação antes de assinar:** `verify_spot_swap_tx`, leitura de `simulation.accounts` e invariante precedem a assinatura ([spot_send.py:144](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:144), [spot_send.py:181](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:181)).
- **Venda não bloqueada pelo estado do interruptor:** a condição contém `is_buy`; erros de Redis/Postgres são absorvidos pelo leitor ([spot_send.py:165](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:165), [kill_switch.py:142](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/kill_switch.py:142)).
- **Assinatura durável antes do broadcast:** a sessão termina antes do envio; `role_session` abre uma transação própria ([spot_send.py:204](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:204), [session.py:231](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:231)).
- **Exceção de envio → `submitted_unconfirmed` está certo.** Evita declarar falha de algo que pode ter sido transmitido. `SendDisabled` é distinguível porque ocorre antes da chamada RPC ([spot_send.py:217](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:217), [tx_rpc.py:239](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx_rpc.py:239)). Aqui o novo código segue o script corrigido e supera a tesouraria, que ainda marca exceção de envio como falha ([treasury_send.py:201](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_send.py:201)).
- **Pending e fill zero permanecem pendentes**, corrigindo os problemas anteriores ([spot_send.py:231](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:231), [spot_send.py:245](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:245)). Isso depende de reconciliação posterior; não equivale a operação liquidada.
- **Prioridade:** teto confrontado com `ceil(limit × price / 10⁶)` verificado ([spot_verify.py:327](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_verify.py:327), [spot_send.py:150](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:150)).
- **Admissão:** decisão recusada retorna antes de `spot_leg`; sizing publicado sozinho não autoriza compra ([spot_entries.py:215](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entries.py:215)).
- **Rent fora de `sol_spent`:** a subtração está correta quando os deltas e a criação observada pertencem à operação ([spot_entry_writes.py:86](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entry_writes.py:86)); o achado 2 compromete essa premissa.

**OBSIDIAN**

- **Spot — a mesa `spot/1`** — registrar os dois bloqueios e a faixa estreita de admissão por custo.
- **Revisoes-Astra/Index** — vincular esta revisão, as reproduções e os 72 testes aprovados.
- **Mesa `spot/1` — placar** — registrar a revisão como pendência técnica, sem acrescentar operações sintéticas.