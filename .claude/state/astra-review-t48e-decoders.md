**RESUMO**

**REQUEST_CHANGES.** A validação binária das caudas está correta; o tratamento de perda de cobertura ainda não fecha todos os consumidores. Separei abaixo defeitos preexistentes expostos pela mudança de lacunas da própria T4.8e.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisei o diff, os arquivos novos, os testes e os consumidores de fill/cobertura.

**TESTES**

Não executei pytest, lint ou typecheck nesta revisão estritamente sem escrita. Portanto, não afirmo que passaram.

A contagem por `Get-Content` dos 12 arquivos de produção listados retornou **83–345 linhas**; todos estão dentro do limite. Os testes novos verificam codecs, contadores e marcação de gaps, mas o teste da launch lane termina em `_fold_logs`, sem verificar a decisão posterior: [test_logs_trades_t48e.py:212](C:/dev/project-hunter/services/meme-worker/tests/test_logs_trades_t48e.py:212).

**MUST-FIX**

1. **HIGH — A launch lane continua produzindo resultado paper após perder o gatilho de saída.**

   `mark_gap` limpa trades, mas preserva pontos de preço. `exit_trigger` consulta o último ponto, o relógio e `latest_trade`, sem verificar cobertura: [event_state.py:230](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_state.py:230), [launch_lane_pricing.py:118](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/launch_lane_pricing.py:118). Após `_fold_logs`, a avaliação continua normalmente: [launch_lane_eval.py:180](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/launch_lane_eval.py:180).

   **Cenário:** aposta aberta; a primeira venda de terceiro chega indecodificável; o gap é marcado, mas `latest_trade=None`. Apostas que deveriam sair nesse evento continuam até o time stop e recebem um resultado normal com outro preço.

   **Correção:** invalidar/censurar a medição afetada até recuperação comprovada. Apenas esperar o tape aquecer não recupera a primeira venda perdida. Este é um fechamento incompleto da T4.8e.

2. **HIGH — Os caminhos do worker aplicam eventos de outros mints da mesma transação.**

   O novo helper recebe `mint`, mas não filtra os eventos antes de entregá-los: [logs_trades.py:83](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/logs_trades.py:83). Os dois consumidores os aplicam diretamente: [event_gate_eval.py:101](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_eval.py:101), [launch_lane_eval.py:70](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/launch_lane_eval.py:70).

   **Cenário:** uma transação negocia A e B, mencionando ambas as PDAs. A assinatura de A recebe também o evento de B; as reservas, o tape e possivelmente a saída de A passam a refletir B.

   **Correção:** filtrar `event.mint == mint` antes de normalizar/aplicar. O executor já faz isso: [event_exits_eval.py:272](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/event_exits_eval.py:272). **É preexistente, não uma regressão criada pela T4.8e**, mas permanece nos dois caminhos alterados.

3. **MEDIUM — Gap nos primeiros cinco segundos ainda permite afirmar “criador não vendeu”.**

   `covered_from_birth` considera apenas `covered_since <= first_seen_at + 5s`, mesmo depois de um gap conhecido: [event_state.py:307](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_state.py:307). Sem venda registrada, isso produz `sold_any=False`: [event_state_values.py:63](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_state_values.py:63).

   **Cenário:** assinatura no nascimento; venda do criador indecodificável em +2s; nenhum outro sell observado. Depois do aquecimento, a leitura volta a afirmar ausência de venda, embora uma tenha sido perdida.

   **Correção:** perda conhecida deve invalidar a cobertura desde o nascimento independentemente da tolerância inicial. Preservar `True` para venda comprovada e retornar desconhecido quando não houver prova. **Também é um defeito preexistente que o novo uso de `mark_gap` não resolve.**

**NICE-TO-HAVE**

- **Gap durável:** registrar perdas de decode com mint, assinatura, slot, horário, motivo e versão do decoder. Hoje o helper marca memória e contador/log; a reconexão já possui persistência via `record_gap`: [logs_trades.py:97](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/logs_trades.py:97), [event_gate_eval.py:312](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_eval.py:312). Reutilizaria a infraestrutura de gaps de memes, com agregação para não inserir uma linha por evento durante uma incompatibilidade generalizada.
- Acrescentar testes de decisão completa: gap seguido de account notification, gap dentro da graça inicial, transação com dois mints e campos variáveis com `shareholders` não vazio.
- Tornar explícito o contrato do fallback PumpSwap: exige transação da nossa ordem já verificada, não uma transação arbitrária.

**O QUE EU FARIA DIFERENTE**

**(1) Caudas:** o offset está correto. Pump.fun valida depois de `ix_name`, `shareholders` e demais campos; PumpSwap aceita exatamente 0/49 bytes e valida o booleano: [trade_event_codec.py:193](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event_codec.py:193), [sell_event.py:155](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/sell_event.py:155).

Isso reconhece **formas binárias compatíveis**, não prova identidade semântica. Um layout futuro com o mesmo tamanho e campos reinterpretados pode passar. Também truncar exatamente uma extensão pode parecer um layout histórico válido. Não considero isso um bloqueador novo: é o limite dessa compatibilidade, que deve ficar documentado.

**(2) Fallback PumpSwap:** isoladamente, **sim**, pode classificar outra transação como venda: basta sucesso e saldos disponíveis; não exige evento nem valida o pagador esperado: [pumpswap_build.py:100](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:100).

Porém, **não identifiquei um caminho normal novo que entregue uma transação alheia**: a reconciliação seleciona a venue da ordem e busca sua assinatura registrada: [exit_settle.py:95](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_settle.py:95), [submit.py:185](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:185). Não trataria o antigo cenário de migração como regressão desta mudança.

**(3) Ordem do gap:** marcar depois de consumir os trades funciona para `tape_minute`, que consulta `covered_since`; o pullback também compara o contador de gaps antes de propor: [event_state.py:253](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_state.py:253), [event_gate_pullback.py:118](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_pullback.py:118). **Não é uma garantia global**, pelos consumidores descritos nos must-fix.

**(4) Executor:** contador/log basta para tornar a perda observável, **não para restaurar proteção por creator sell**. Um evento perdido não altera `creator_sold`; account notifications continuam avaliando preço: [event_exits_eval.py:230](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/event_exits_eval.py:230), [event_exits_eval.py:260](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/event_exits_eval.py:260).

Eu registraria degradação por posição e solicitaria reconciliação do evento perdido. Manteria stops por preço funcionando. Não transformaria “evento desconhecido” automaticamente em `creator_dump`: isso inventaria uma venda e mudaria a política de saída.

**CONCORDO COM**

- Cauda desconhecida exposta, sem entrar na aritmética financeira: [trade_event_codec.py:128](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event_codec.py:128), [sell_event.py:101](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/sell_event.py:101).
- Separar ausência de trade de falha de decode: [trade_event.py:127](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event.py:127).
- Preservar o pino: continua em **T4.8d / slot 449734335**, sem diff; decodificar eventos novos não equivale a aprovar o programa novo: [program_identity.py:126](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_identity.py:126).

**OBSIDIAN**

- **Revisões Astra — T4.8e:** registrar este parecer e distinguir defeitos herdados de correções incompletas.
- **Meme (Mercado):** documentar layouts aceitos, caudas sem interpretação e cobertura degradada.
- **EXP-M18 — Sniper de lançamento:** acrescentar a limitação de medição após perda do evento de saída, sem reescrever o protocolo.
- **Open Bugs:** registrar mistura entre mints, cobertura falsa dentro da graça inicial e ausência de censura na launch lane.