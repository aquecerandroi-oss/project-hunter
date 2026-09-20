**RESUMO**

Como `risk-engine-guardian`: **(1) FECHADO; (2) PARCIALMENTE FECHADO.**

**ARQUIVOS**

Nenhum arquivo alterado.

**TESTES**

`uv run pytest services/meme-executor/tests/test_spot_money_path.py services/meme-executor/tests/test_spot_exit_rules.py -q -p no:cacheprovider`

Saída: `63 passed in 1.31s`. Bytecode/cache desabilitados. Reproduções adicionais em memória, com fakes.

**MUST-FIX**

- [spot_send.py:254](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:254) — **ALTA, residual do achado 2** — compra valida apenas delta positivo de tokens — cenário reproduzido: meta com delta SOL zero e tokens positivos retorna `confirmed`; permite novamente o `ticket_fallback` de [spot_entry_writes.py:90](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entry_writes.py:90).
- [spot_send_rules.py:167](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:167) — **ALTA, novo** — lista de tokens ilegível vira lista vazia — cenário reproduzido: `preTokenBalances=None` com pós-saldo positivo confirma a compra, interpretando saldo anterior desconhecido como zero e inferindo ATA criada.

**NICE-TO-HAVE**

Nenhum adicional.

**O QUE EU FARIA DIFERENTE**

Rejeitar metadados incompletos e exigir gasto SOL válido antes de confirmar compra.

**CONCORDO COM**

- [spot_send.py:200](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:200) — **ALTA anterior, FECHADA** — releitura após o invariante — mudança durante a simulação bloqueia compra antes da assinatura.
- [spot_send.py:241](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:241) — **atribuição corrigida** — fill pela assinatura — aporte externo na janela não contamina mais o gasto.

**OBSIDIAN**

- **Spot — a mesa `spot/1`** — registrar fechamento do kill switch e as duas pendências de validação do fill.
- **Revisoes-Astra/Index** — vincular esta re-revisão e suas reproduções.