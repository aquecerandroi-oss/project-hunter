**RESUMO**

Aceito **A sem prioridade/quota nova**, com uma correção obrigatória: **`history` não prova origem em pedido de backfill**. A identidade pelo lote efetivamente inserido está correta sob a persistência atual. Documentar o consumo futuro pelo scanner também está correto, com contrato explícito.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão do código atual, HEAD `4ee792f`, considerando o commit `3dcb218`.

**TESTES**

Não executei testes; fiz inspeção estática. Não há resultado de execução funcional a declarar.

**MUST-FIX**

**(a) A equivalência estrutural é falsa: falta considerar o envelhecimento.**

`check_gaps` cria lacunas dentro da janela, mas recalcula `live_from` a cada ciclo. `pending_gaps` classifica exclusivamente por `gap_end >= live_from` ou `< live_from`, sem consultar a origem: [recovery.py:180](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:180), [recovery_queries.py:205](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_queries.py:205), [recovery_queries.py:215](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_queries.py:215).

**Cenário concreto:** a detecção registra um buraco recente; REST permanece indisponível, ou o processo para por 26 horas. Na retomada, o mesmo buraco pertence a `history`, embora nenhum `market.backfill.requested` tenha existido. Nem `failed` impede isso: há reabertura posterior sem mudar os limites da lacuna — [recovery_queries.py:151](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_queries.py:151). Uma lacuna de `report_losses` também pode envelhecer; sua criação preserva o `open_time` perdido — [persist.py:135](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:135).

Portanto, trocaria o motivo por **`reason="historical_recovery"`**, mantendo `source="rest"`. Sem migration, isso descreve exatamente o que sabemos. A afirmação anterior em `.claude/state/notes-T2.5.md:529` e no comentário de [recovery_queries.py:184](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_queries.py:184) também precisa ser corrigida.

**NICE-TO-HAVE**

**(b) Aceito A sozinha; não exigiria B como defesa abstrata.** A queda para até seis anúncios por ciclo é convincente para reduzir a pressão nova do estrato histórico. Ressalvas concretas:

- O limite é **por execução de recovery/shard**, não global: [recovery.py:177](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:177).
- **240× menos eventos não significa 240× mais histórico recuperado.** Mantendo seis lacunas de 240 minutos, continua o teto de 1.440 minutos recuperados por ciclo para esses pedaços: [backfill_plan.py:43](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill_plan.py:43), [recovery.py:47](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:47).
- A mudança não compacta eventos antigos já pendentes. Eles continuam sendo selecionados por `(created_at, id)`: [outbox_store.py:210](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:210).

Assim, aprovaria a redução de volume; “a espera deixou de ser problema prático” deve ser conclusão da medição de backlog e latência após a mudança. Não proponho alteração em `outbox.py` agora.

**O QUE EU FARIA DIFERENTE**

Definiria o novo evento como **notificação de inserção histórica**, com estas garantias:

- `count > 0`; lote vazio não gera evento.
- `[start, end)` envolve os minutos inseridos, **sem prometer continuidade nem conclusão do gap/pedido**.
- Velas, agregado e atualização do gap compartilham a mesma transação/savepoint.
- Consumidores relêem o banco para verificar cobertura.

A transação existente oferece o ponto certo para isso: [recovery_drain.py:92](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_drain.py:92).

**CONCORDO COM**

**(c) A identidade pelo lote realmente inserido está certa.** Usaria exatamente o resultado de `INSERT … RETURNING`, já disponível em [persist_rows.py:141](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:141).

A justificativa precisa ser mais precisa: **subconjuntos diferentes podem ter os mesmos extremos**, em geral. Porém, aqui, dois lotes efetivamente inseridos e commitados para a mesma chave de mercado/timeframe são disjuntos, porque o conflito impede reinserir o mesmo minuto — [persist_rows.py:136](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:136). Portanto, não podem compartilhar o mesmo mínimo. Isso sustenta sua identidade sem exigir hash de todos os minutos.

Após rollback, o evento também desaparece; após commit, retry só anuncia novos minutos. Preservar essa atomicidade é essencial. Não vejo contraexemplo no fluxo atual sem remoção/reinserção de candles.

**(d) Correto deixar a implementação no scanner para T2.5d/T2.5e.** Documentaria como requisito: invalidar ou reagendar o bootstrap afetado, tratar duplicatas, reler cobertura e manter recuperação por releitura periódica/restart. O agregado não deve marcar bootstrap como completo.

Hoje já existe retomada de bootstrap incompleto por `retry_at`, independente desse novo stream: [ledger.py:216](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/ledger.py:216). Logo, o evento pode antecipar a reação; não deve virar sua única garantia.

Também concordo em preservar os anúncios individuais do estrato `live`. Para histórico muito antigo, o strategy-worker já rejeita avaliação por atraso, com padrão de 300 segundos: [decide.py:97](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:97), [config.py:55](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/config.py:55). Os outcomes têm varredura independente: [consumer.py:201](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:201).

**OBSIDIAN**

- **Market Collector** — registrar que os estratos representam idade, incluindo lacunas recentes envelhecidas; descrever a agregação.
- **Data Flow** — documentar `market.candles.backfilled`, atomicidade e intervalo sem garantia de continuidade.
- **Features** — registrar o requisito de invalidação/reagendamento do bootstrap e recuperação sem depender exclusivamente do evento.
- **Revisões Astra / T2.9c** — registrar a correção da premissa anterior e a aceitação de A sem quota adicional.