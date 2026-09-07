**RESUMO**

Como `risk-engine-guardian`: **DONE_WITH_CONCERNS**. Os cenários originais de **1 e 2 fecharam**; **3, 4 e 5 fecharam parcialmente**. Há também falhas de identidade e disponibilidade dos dados.

**ARQUIVOS**

Nenhum criado ou modificado; nenhum commit.

**TESTES**

Sondas em memória: `uv run python -B -`. Saída real:

```text
rejected EntryWithoutApproval
oversize EntryWithoutApproval
crossings: target 101 stop 102
invalid trade_id_not_numeric 100
not_received trade_not_yet_received 100
missing_avg_book pending_degraded True True None 10
direct_terminal_attempt: filled 2
BTC_decision_ETH_book: filled 3 3
unreceived_filter_reference filled 3
```

Não reexecutei pytest/ruff/pyright; os 92+6 verdes são os resultados informados.

**MUST-FIX**

- **3 — HIGH, parcial:** a bicondicional e as guardas dos helpers estão corretas, mas `ExitAttempt(...)` diretamente aceita intenção terminal; o adaptador executa sem verificar `live`. **Cenário reproduzido:** intenção `voided` vende outras duas unidades. Validar também no construtor. [intents.py:122](C:/dev/project-hunter/packages/core/hunter_core/execution/intents.py:122), [paper.py:155](C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:155).
- **4 — HIGH, parcial:** antes do fill, corrigido; depois dele, `is_untradable` ainda transforma qualquer reprovação em resíduo. **Cenário reproduzido:** intenção de 10, tentativa de 2, máximo permitido de 5, fill de 1 → nove unidades classificadas como `below_min_qty`, embora possam ser vendidas em tentativas menores. [pricing.py:189](C:/dev/project-hunter/packages/core/hunter_core/execution/pricing.py:189), [paper.py:191](C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:191).
- **5 — parcial:** separou corretamente gatilho e observação atual, mas perdeu `received_at`; `triggered_at` recebe `trade_ts`, sem instante distinto da avaliação. **Cenário:** recepção atrasada fica indistinguível de disparo imediato, impedindo reconstruir quando a proteção pôde agir. [intents.py:180](C:/dev/project-hunter/packages/core/hunter_core/execution/intents.py:180), [triggers.py:91](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:91).
- **Identidade — HIGH:** carregar a decisão não vincula o livro ao mercado aprovado. **Reprodução:** decisão BTC + livro ETH → compra preenchida. Comparar identidades antes do cálculo. [paper.py:100](C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:100).
- **Disponibilidade — HIGH:** o filtro recebe `last_trade.price` sem validação temporal. **Reprodução:** `avg_price_mins=0`, negócio ainda não recebido → entrada preenchida. A correção temporal ficou restrita aos gatilhos; a marcação do resíduo também ignora recepção. [paper.py:101](C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:101), [pricing.py:158](C:/dev/project-hunter/packages/core/hunter_core/execution/pricing.py:158).

**NICE-TO-HAVE**

Nenhum adicional.

**O QUE EU FARIA DIFERENTE**

Para **T3.5**, exigiria no relatório **ou envelope obrigatório**, hoje incompleto em [adapter.py:126](C:/dev/project-hunter/packages/core/hunter_core/execution/adapter.py:126), somente estes campos bloqueantes:

- Escopo validado: organização, carteira, mercado e identidade SPOT; vínculo imutável à decisão persistida.
- Namespace do livro consumido e watermark resultante da avaliação, inclusive sem fill.
- Evidência causal completa: negócio, evento, recepção e instante da avaliação.
- Referência efetiva dos filtros: valor, fonte, janela, disponibilidade e snapshot dos filtros.
- Snapshot dos parâmetros efetivos das políticas, ou referência imutável que os resolva.

Podem vir das entidades travadas; não precisam ser colunas duplicadas. A divisão dos módulos é adequada, mas deixou as verificações acima inconsistentes entre caminhos.

**CONCORDO COM**

Decisão obrigatória e teto de quantidade; avanço alvo/101 → stop/102; argumentos adicionais no Protocol. [entries.py:63](C:/dev/project-hunter/packages/core/hunter_core/execution/entries.py:63), [triggers.py:185](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:185), [adapter.py:308](C:/dev/project-hunter/packages/core/hunter_core/execution/adapter.py:308).

**OBSIDIAN**

- **Execution Engine** — registrar fechamento parcial e envelope obrigatório da T3.5.
- **Paper Trading** — registrar regressões de terminal, resíduo, identidade e disponibilidade.