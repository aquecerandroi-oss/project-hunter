**RESUMO**

**DONE_WITH_CONCERNS — dois must-fix no ciclo de vida das gerações.** O uso de `system_events` é compatível com os grants e o particionamento existentes. Não encontrei cenário comprovado de vazamento de conexão introduzido pelo diff; há disputa pelo pool e possibilidade conhecida de duplicação.

A revisão considera a decisão anterior de deduplicar no leitor, registrada em [meme-cycle-metrics.md:84](/C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/meme-cycle-metrics.md:84).

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisei os quatro módulos, os seis arquivos `test_cycle_*.py`, contrato, migrações, sessão e implementação local do SQLAlchemy.

**TESTES**

Não executei pytest, migrações ou consultas ao banco nesta revisão estritamente somente leitura. Portanto, não confirmo resultados anteriores nem os grants efetivamente implantados.

Inspeção executada:

```text
git diff --numstat -- services/meme-worker/hunter_meme_worker/main.py
19	3	services/meme-worker/hunter_meme_worker/main.py
```

Os testes existentes não fecham dois pontos:

- O teste de desligamento chama `cycles.close()` diretamente, sem passar por `run_meme`: [test_cycle_history_contract.py:159](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_history_contract.py:159).
- O fake de banco substitui integralmente `role_session`; o cancelamento testado não exercita checkout, COMMIT ou limpeza reais: [test_cycle_history.py:55](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_history.py:55).

**MUST-FIX**

1. **HIGH — crash pode receber certificado de desligamento limpo.**

   **Cenário:** `chain_once` lança uma exceção; `forever` a relança, o `TaskGroup` cancela os demais laços e entra no `finally`. Se os fechamentos anteriores terminarem e o banco responder, `cycles.close()` grava `generation_end` para ambos os laços.

   Evidências: [collect.py:337](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/collect.py:337), [main.py:324](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:324), [cycle_wiring.py:68](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_wiring.py:68). Isso contradiz o contrato de “somente desligamento limpo” em [cycle_history.py:18](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:18).

   **Correção recomendada:** separar drenagem de classificação do término. Drenar também após falha, mas emitir término limpo somente quando essa causa estiver demonstrada; alternativamente, registrar explicitamente a causa no evento.

   A recíproca também precisa ser corrigida: **ausência de `generation_end` significa término não comprovado**, não necessariamente crash. Um SIGTERM normal com banco indisponível também perde esse evento, pois `drain` termina ao primeiro flush malsucedido: [cycle_history.py:284](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:284).

2. **MEDIUM — `MEME_ENABLED=false` nunca persiste a geração anunciada.**

   **Cenário:** processo inicia desligado; `announce()` enfileira dois `generation_start`, publica no Redis e retorna. `run_meme` espera indefinidamente antes de criar o gravador e antes do `try/finally`. Mesmo um cancelamento normal não chama `close()`. O histórico não consegue distinguir esse período desligado de ausência de evidência.

   Evidências: [cycle_wiring.py:46](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_wiring.py:46), [main.py:181](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:181), [main.py:189](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:189), [main.py:320](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:320).

   **Correção recomendada:** manter o gravador supervisionado também no ramo desligado e cobrir esse ramo pelo fechamento. Testar o caminho real de `run_meme`, incluindo cancelamento.

**NICE-TO-HAVE**

Respostas às demais perguntas e ressalvas:

**(1) Global, INSERT e partições: sim.** `system_events` não tem `organization_id`; é global, sem RLS de tenant. Está na classe append-only e recebe `INSERT` para `hunter_worker`: [DATABASE.md:503](/C:/dev/project-hunter/docs/DATABASE.md:503), [tables.py:39](/C:/dev/project-hunter/infra/migrations/ddl/tables.py:39), [grants.py:78](/C:/dev/project-hunter/infra/migrations/ddl/grants.py:78).

A escrita **pela pai** funciona sem grant direto nas filhas; o projeto deliberadamente revoga esse acesso direto: [partitions.py:25](/C:/dev/project-hunter/infra/migrations/ddl/partitions.py:25). Falta de partição do mês é outro problema: o INSERT falha e a fila permanece para retry; não se resolve concedendo privilégios.

**(2) Volume e consulta: adequados em princípio, sem benchmark.** A conta nominal é `1.440 + 5.760 = 7.200` ciclos/dia, cerca de **216 mil em 30 dias**, além de marcadores e retries. A cadência inclui trabalho mais pausa, portanto esse número é aproximado; o contrato da medição explicita isso em [cycle_metrics.py:15](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:15). A retenção mensal pode manter mais de 30 dias: [DATABASE.md:131](/C:/dev/project-hunter/docs/DATABASE.md:131).

O índice `(component, created_at)` atende igualdade por componente e limite temporal. **Não atende sozinho** os filtros JSON nem a ordenação do `DISTINCT ON`; esses exigem processamento adicional. Não criaria outro índice sem `EXPLAIN (ANALYZE, BUFFERS)` com volume representativo: [0001_initial_schema.py:371](/C:/dev/project-hunter/infra/migrations/versions/0001_initial_schema.py:371), [cycle_history.py:98](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:98).

**Atraso de persistência superior a um dia não exclui a linha:** o filtro é um limite inferior de `created_at`, sem limite superior. A frase contrária em [cycle_history.py:112](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:112) está errada. Sob relógios coerentes, o predicado é seguro. Pode excluir uma linha válida por `ended_at` se o relógio do worker estiver mais de um dia adiantado em relação ao banco; UTC não garante sincronização entre máquinas.

**(3) Pool e cancelamento: há compartilhamento, mas não vazamento demonstrado.** As fábricas usam o mesmo `runtime.engine`: [main.py:117](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:117), [main.py:160](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:160), [main.py:181](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:181). O gravador pode ocupar uma conexão enquanto os laços aguardam outra. Os padrões são cinco conexões mais cinco de overflow: [settings.py:53](/C:/dev/project-hunter/packages/core/hunter_core/settings.py:53).

O timeout envolve aquisição, contexto, INSERT e saída transacional: [cycle_history.py:248](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:248), [session.py:232](/C:/dev/project-hunter/packages/core/hunter_core/db/session.py:232).

- **Durante checkout:** pode cancelar antes de qualquer INSERT. O SQLAlchemy local trata falha de aquisição e protege o fechamento da sessão: [.venv/session.py:1068](/C:/dev/project-hunter/.venv/Lib/site-packages/sqlalchemy/ext/asyncio/session.py:1068), [.venv/base.py:714](/C:/dev/project-hunter/.venv/Lib/site-packages/sqlalchemy/pool/base.py:714). Isso é consistente com a [documentação de fechamento de sessões](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#closing).
- **Durante COMMIT:** o resultado pode ser indeterminado para o cliente. O banco pode ter confirmado e o código não alcançar o ACK da fila; o retry duplica fisicamente. O `DISTINCT ON` trata essa identidade lógica: [cycle_history.py:99](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:99), [cycle_history.py:264](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:264).
- **10 segundos não são teto rígido de retorno:** o cancelamento inicia a limpeza; rollback/fechamento podem prolongá-la. O próprio helper documenta esse problema e configura `command_timeout=30`: [session.py:11](/C:/dev/project-hunter/packages/core/hunter_core/db/session.py:11), [session.py:103](/C:/dev/project-hunter/packages/core/hunter_core/db/session.py:103). A mesma ressalva vale para os três segundos do `close()`.

Acrescentaria testes reais de timeout durante checkout/execução e reutilização posterior do pool. Não classificaria vazamento como must-fix sem reprodução.

**(4) UUID v4: desvio, com precedente documentado.** A regra geral exige v7 da aplicação; o INSERT novo gera v4 no banco: [DATABASE.md:9](/C:/dev/project-hunter/docs/DATABASE.md:9), [cycle_history.py:94](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:94). Há exceção explícita para `meme_decision_tapes`, citando `meme_gate_refusals_by_mint`: [DATABASE.md:8150](/C:/dev/project-hunter/docs/DATABASE.md:8150).

O precedente não autoriza silenciosamente este escritor. Recomendo usar v7 ou registrar a exceção específica. **Trocar apenas por v7 não elimina duplicatas**, porque a PK é `(created_at, id)`: [DATABASE.md:590](/C:/dev/project-hunter/docs/DATABASE.md:590).

**(6) Cancelamento externo: propaga nos awaits novos inspecionados.** Os handlers capturam `Exception`, não `BaseException`; `CancelledError` atravessa publicação, flush e drenagem. O timeout próprio vira falha contada; cancelamento externo não: [cycle_metrics.py:180](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:180), [cycle_history.py:220](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:220), [cycle_history.py:267](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:267). Propagação não significa conclusão instantânea da limpeza.

**O QUE EU FARIA DIFERENTE**

Manteria a arquitetura sem migração, corrigindo primeiro os dois caminhos de término. Tornaria explícitos três limites: persistência sujeita a perda da fila, duplicatas deduplicadas pelo leitor e término desconhecido quando falta certificado. Evitaria prometer “ao menos uma” incondicionalmente: a fila descarta e desaparece com o processo ([cycle_history.py:134](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:134)).

**CONCORDO COM**

- Duração monotônica, timestamp UTC e registro somente de ciclos concluídos: [cycle_metrics.py:225](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:225).
- Fila limitada, ACK por token e lotes de até 500: [cycle_history.py:85](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:85), [cycle_history.py:195](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:195).
- Deduplicação antes dos percentis e janela por `ended_at`: [cycle_history.py:98](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:98).
- Congelar a base prospectiva e exigir cobertura antes de julgar a guarda: [EXP-M26:539](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M26-grafico-em-moedas-maduras.md:539).

**OBSIDIAN**

- **meme-cycle-metrics** — acrescentar os dois must-fix e corrigir “sem fim = crash” para “término não comprovado”.
- **Meme — o que uma estratégia é aqui** — esclarecer pool compartilhado, duplicatas, perdas possíveis e limites dos timeouts.
- **EXP-M26 — gráfico em moedas maduras** — registrar que a revisão de banco identificou pendências no certificado das gerações antes do aceite da instrumentação.