**RESUMO**

**REQUEST_CHANGES** por três pontos: marca definitiva após recorte temporal, orçamento histórico incompleto e um escritor de gaps fora do protocolo de lock.

Respostas diretas:

- **(i)** A extração preservou os filtros de finalização, a transação candles/outbox/status e o tratamento de indisponibilidade da coordenação REST. O problema está no orçamento do escalonamento, descrito abaixo. [recovery_drain.py:68](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_drain.py:68)
- **(ii)** `complete/final` funciona para o teto de linhas e as barreiras, mas perde informação sobre o sufixo temporal recortado. Há também reavaliação indefinida possível quando falta partição ou a fonte nunca entrega os minutos bloqueados. [backfill_plan.py:143](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill_plan.py:143)
- **(iii)** Aceito o lock por exchange como escolha inicial: ambos os planejadores o tomam antes da cobertura, sem fetch de candles na seção crítica. Não há medição suficiente para reprovar sua granularidade por latência; falta incluir o terceiro escritor. [recovery.py:96](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:96), [backfill.py:223](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill.py:223)
- **(iv)** Um `failed` histórico **é elegível à reabertura**, mesmo fora da janela de detecção, desde que o mercado continue no universo consultado. Isso não garante recuperação: fonte permanentemente vazia continuará falhando, e histórico pode ficar sem atendimento enquanto o estrato vivo consumir todo o orçamento. [recovery.py:112](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:112), [recovery_queries.py:151](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_queries.py:151), [recovery_queries.py:210](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_queries.py:210)
- **(v)** **Causa indeterminada.** O timeout de 10 s envolve `flush_batch` inteiro; a linha citada não prova que o COMMIT sozinho demorou 10 s. Pode ser pressão adicional de banco ou carga de partida. O relato não traz tempos por fase nem espera de locks para distinguir. [persist.py:203](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:203), [t25-proof.md:491](C:/dev/project-hunter/.claude/state/t25-proof.md:491)

**ARQUIVOS**

Revisei os arquivos novos e modificados indicados e suas dependências relevantes. Nenhum arquivo criado/modificado por mim; nenhum commit. A tarefa paralela de scanner/indicators ficou fora da revisão.

**TESTES**

Executei com sincronização do ambiente, bytecode e cache do pytest desabilitados:

```text
uv run pytest services/market-worker/tests/test_backfill_plan.py -q
17 passed, 1 warning in 1.76s
```

O aviso foi `Unknown config option: asyncio_mode`, pois desabilitei o carregamento automático de plugins.

Executei também duas reproduções em memória, via `uv run python -`, sobre as funções reais:

```text
requested=[10:00,10:30); accepted= 2026-09-06T10:00:00+00:00 2026-09-06T10:05:00+00:00
complete= True truncated= False deferred= 0 blocked= 0

history_start_s= 45.0 fetch_timeout_s= 20.0
cycle_elapsed_s= 81.0 history_elapsed_s= 36.0
```

A segunda usa **tempos simulados**, não medição do stack. `git diff --check` nos caminhos revisados não apontou erros de whitespace, apenas avisos CRLF/LF. Não executei integração, lint ou typecheck nesta rodada.

**MUST-FIX**

1. **HIGH — janela parcialmente futura recebe marca definitiva.**  
   [backfill_plan.py:172](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill_plan.py:172) recorta o fim, mas não registra os minutos temporariamente excluídos. [backfill.py:281](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill.py:281) transforma `plan.complete` diretamente em `final`.

   **Cenário:** pedido `[10:00,10:30)`, `detection_last=10:05`; são planejados seis minutos e o evento inteiro é marcado. A republicação após 10:30 é descartada pela guarda, embora 24 minutos nunca tenham sido planejados por esse pedido. A detecção periódica pode recuperar parte deles, mas isso não corrige o contrato do consumidor.

   **Correção:** carregar explicitamente o recorte temporal e impedir `final=True` enquanto houver sufixo temporariamente excluído. Testar republicação do **mesmo `event_id`** após o avanço do relógio.

2. **HIGH — os 30 s não limitam a operação histórica inteira nem respeitam a próxima detecção.**  
   O deadline nasce **depois** do estrato vivo, e `remaining` limita somente o fetch. Leitura inicial, aquisição de conexão, lock de linha e persistência ficam fora desse timeout. [recovery.py:161](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:161), [recovery_drain.py:139](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_drain.py:139), [recovery_drain.py:157](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_drain.py:157)

   **Cenário reproduzido:** vivo consome 45 s; histórico consome 8 s de banco + 20 s de REST + 8 s de banco. Resultado: **36 s históricos e ciclo de 81 s**, apesar dos limites declarados.

   **Correção:** calcular o prazo também pela próxima detecção e propagá-lo pela unidade inteira de recuperação, preservando rollback e sem contabilizar esgotamento do orçamento como falha do gap.

3. **MEDIUM — há um terceiro criador de gaps sem advisory lock.**  
   `persist.report_losses()` também consulta cobertura e insere gaps, sem participar da serialização. [persist.py:109](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:109), [persist.py:127](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:127)

   **Cenário:** persistência descarta uma vela atrasada; `report_losses` e o consumidor leem simultaneamente “ausente, sem gap”. Ambos inserem intervalos sobrepostos. O lock entre consumidor e detecção não impede essa corrida.

   **Correção:** incluir esse escritor no mesmo protocolo, antes da leitura de cobertura, e testar a concorrência consumidor × perdas. A corrida entre escritores antigos já existia; o novo consumidor também fica exposto. Isso exige ampliar pontualmente o escopo para `persist.py`.

**NICE-TO-HAVE**

- **Corrigir o teste de timeout após a extração.** Ele ainda altera `recovery.FETCH_TIMEOUT_S`, mas chama uma função cujo argumento padrão já vale 20 s. O adapter termina em 10 s, e as asserções podem passar sem timeout algum. Passar `timeout_s=0.05` e verificar cancelamento. [test_recovery.py:290](C:/dev/project-hunter/services/market-worker/tests/test_recovery.py:290), [recovery_drain.py:48](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_drain.py:48)
- **Alinhar observabilidade com `complete`.** Com chunks novos e minutos bloqueados por outro gap, pode sair `accepted` embora `final=False`: `outcome_name` não considera `blocked_minutes`. [backfill_plan.py:320](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill_plan.py:320)
- **Tratar 240 como tamanho de lote, não garantia de prontidão.** Dois chunks rápidos podem acumular 480 anúncios antes da drenagem, além dos vivos. A aritmética `240 + 200` não limita o backlog agregado. [recovery.py:162](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:162)
- Acrescentar prova de progresso em republicações sucessivas após truncamento por linhas e após provisionamento da partição ausente.

**O QUE EU FARIA DIFERENTE**

Manteria o lock por exchange e mediria separadamente espera, duração da seção crítica e fases do flush antes de mudar a granularidade ou atribuir o traceback à contenção.

O teto final de sete dias é coerente **com a política declarada**, mas não atende sozinho à referência de trinta dias: o código pressupõe que alguém peça o restante em outra janela. Essa limitação precisa ficar explícita no aceite do regime. [backfill_plan.py:38](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill_plan.py:38), [M2.md:57](C:/dev/project-hunter/docs/plans/M2.md:57)

**CONCORDO COM**

- ACK sem marca para recusas temporárias e planejamento parcial; marca após a transação. [backfill.py:159](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill.py:159)
- Barreira de gaps ausentes `open/failed`, preservando o cooldown. [backfill_plan.py:217](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill_plan.py:217)
- Isolamento de envelopes ilegíveis e verificação prévia das partições. [backfill_reader.py:51](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill_reader.py:51), [backfill.py:227](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill.py:227)

**OBSIDIAN**

- **Market Collector** — registrar os três escritores de gaps, o protocolo de lock e os limites reais do orçamento.
- **Data Flow** — distinguir janela solicitada, janela aceita, planejamento definitivo e recuperação concluída.
- **Workers** — registrar reavaliação, cooldown e ausência de garantia de progresso sob saturação.
- **Revisões da Astra — T2.5-backfill** — guardar REQUEST_CHANGES, reproduções e critérios de fechamento.
- **Diário — 2026-09-06** — registrar o timeout como causa ainda não determinada, separando relato operacional de diagnóstico.