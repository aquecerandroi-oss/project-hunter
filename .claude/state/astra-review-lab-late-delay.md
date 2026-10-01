**RESUMO**

Seu diagnóstico principal se sustenta: **os `late:delay` registrados pertencem ao incidente de 06–10/09; não demonstram saturação persistente atual.** Eu escreveria “incidente histórico mitigado, com picos residuais e cobertura incompletamente observada”. Os atrasos de até 94 s posteriores são reais, pelos seus dados, mesmo sem cruzar o limiar de recusa.

Isso é coerente com [KB-0089](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0089-o-teto-de-cpu-de-um-processo-so.md) e o [diário de 11/09](C:/dev/project-hunter/obsidian/09-OPERATIONS/Diario/2026-09-11.md). Não encontrei evidência adicional que demonstre saturação corrente.

**ARQUIVOS**

Nenhum criado ou modificado. Revisão no escopo de `backend-specialist`, somente leitura.

**TESTES**

Não executei suítes nem repeti as consultas na VPS. Os números operacionais são os fornecidos por você, confrontados com código e memória.

Conferência aritmética em PowerShell, saída real:

```text
daily_total=1927
perp_plus_spot=1927
```

**MUST-FIX**

1. **Corrigir a população da distribuição diária.**  
   `18 + 10 + 105 + 1.637 + 157 = 1.927`, enquanto você informa **1.743 perp + 184 spot**. Portanto, essa distribuição não pode estar corretamente rotulada como “perp prospectivo” ao mesmo tempo que os totais. A auditoria anterior confirma a separação 1.743/184 na seção 2.

   **Cenário de falha:** calcular percentuais com numerador misturando spot e perp e denominador apenas perp, distorcendo a intensidade do incidente. Reconciliar também os percentuais por versão.

2. **Não tratar `delay_s` como correção suficiente do viés de seleção — pergunta (b).**  
   A válvula retorna antes de avaliar; o portão de elegibilidade também retorna sem sinal. Acrescentar `delay_s` como covariável entre sobreviventes não recupera essas observações nem os outcomes das entradas que não aconteceram. Referências: [consumer.py:138](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:138), [decide.py:134](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:134).

   **Cenário de falha:** concluir que uma estratégia funciona em rajadas usando principalmente as entradas que conseguiram sobreviver à rajada.

   A associação observada justifica marcar o intake como degradado. Contudo, número de **sinais emitidos** é uma aproximação da carga: também depende do roster, dos gatilhos e dos episódios. Não identifica sozinho quanto da diferença entre versões foi causado pelo processamento.

3. **Restringir a conclusão do item 6 — pergunta (e).**  
   Sustenta-se: **“nos 56 sinais persistidos dessa janela, não houve pico ≥60 s”**. Não está demonstrado: **“todas as barras foram avaliadas pelo processo SHARDS=1”**.

   O consumidor lê mensagens antes de concluir o handler; há recusas que recebem ACK sem avaliação. Referências: [consume.py:219](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:219), [consumer.py:260](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:260), [pre_dispatch.py:76](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pre_dispatch.py:76).

   **Cenário de falha:** o grupo avança, parte das barras é recusada, e `last-delivered` é interpretado como cobertura completa. Além disso, com os shards antigos ativos, parte dos sinais pode ter sido gravada por eles; os episódios compartilhados impedem atribuir o resultado agregado exclusivamente ao processo SHARDS=1 ([decide.py:180](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:180)).

   Os 980 descartes são compatíveis com drenagem do backlog antigo. Não provam, individualmente, que aquelas barras já tinham sido avaliadas. **Nada disso demonstra um pico oculto; limita a força da conclusão.**

**NICE-TO-HAVE**

- **Medir o sweep antes de alterá-lo — concordo com (c3).** Ele roda apenas no shard 0, compartilha o conjunto de tarefas do consumidor e disputa os mesmos locks de episódios. Isso torna a hipótese plausível, sem estabelecer causalidade ([outcome_sweep.py:64](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/outcome_sweep.py:64), [outcome_sweep.py:102](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/outcome_sweep.py:102), [main.py:64](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/main.py:64)). Mediria duração, quantidade de acompanhamentos visitados e atraso do event loop, correlacionados temporalmente com o lag. A cadência é **duração da passagem + 10 s**, não necessariamente uma passagem a cada 10 s.
- **Separar espera no dispatcher.** O `queue_wait` atual é observado antes de `dispatcher.submit`; portanto, seus 99,1% abaixo de 1 s não cobrem toda a espera interna ([consumer.py:305](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:305)).

**O QUE EU FARIA DIFERENTE**

**Janela — (b).** Para a análise principal, adotaria conservadoramente:

**`06/09/2026 00:00Z ≤ source_bar_close < 11/09/2026 00:00Z`.**

É um recorte operacional por dias completos, não uma afirmação de que todas essas horas estavam degradadas. Inclui os casos de 06–07/09 e evita declarar recuperação exatamente às 21Z com evidência apenas horária. Usaria sua janela **08/09 12Z–10/09 21Z como sensibilidade secundária**.

Separaria resultados do período degradado e do posterior, mantendo as contagens históricas. Comparações entre períodos precisam controlar a mudança de universo e roster; a KB-0089 registra a redução de aproximadamente 200 para 16 mercados. O diário de 11/09 também registra indisponibilidade do Redis: esse dia não ganha certificado de cobertura perfeita por estar fora do incidente principal.

**Instrumentação — (c).**

1. Aprovo `hunter_shadow_bar_lag_seconds`, observado após validar a vela final e antes da válvula. Seu escopo seria **barras admitidas pelo filtro de shard/universo que chegam ao handler**, inclusive sem sinal; filtros anteriores já existem ([pre_dispatch.py:62](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pre_dispatch.py:62)).
2. Para histórico auditável, escolheria **Postgres**, com denominador de barras recebidas e distinção entre:
   - recusas por **barra**;
   - indisponibilidades por **barra × versão**, preservando o motivo.

   Hoje `UNAVAILABLE` é contado por estratégia/estado, sem motivo na métrica ([metrics.py:50](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/metrics.py:50)). Um contador diário simples precisa definir reentregas: incremento seguido de falha antes do ACK pode contar duas vezes. Agregação em memória com flush periódico, por sua vez, continua perdendo o último lote em crashes.
3. Para monitoramento operacional, scrape histórico das métricas é a alternativa mais simples. **Não equivale a um registro exato de cobertura**, porque pode perder incrementos entre scrapes/restarts. Não chamaria Redis de durável sem verificar sua política efetiva de persistência.

**CONCORDO COM**

**(a)** A evidência aponta para recuperação sustentada dos sinais observados. A ressalva do seu item 9 está correta: `decision_lag` só é observado quando há escrita de sinal ([decide.py:254](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:254)).

**(d)** A equivalência está correta **para fechamento em minuto cheio e limite de 120 s**. Sendo `L = decision_at − source_bar_close`:

```text
delay_s = 60 × (floor(L / 60) + 1)
delay_s > 120 ⇔ L ≥ 120
```

Assim, `119,999 s → delay_s=120`; `120 s → delay_s=180`. Isso decorre da abertura **estritamente posterior** à decisão ([plan.py:48](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/plan.py:48)). O limiar implementa o contrato; não encontrei bug nessa comparação.

Uma precisão adicional: os quatro `missed_open` mostram decisões tomadas perto da fronteira, não necessariamente **commits** naquele instante. `emitted_at` recebe `decision_at`; a confirmação posterior pode chegar depois da abertura ([persist.py:93](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:93), [confirm.py:76](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/confirm.py:76)).

**OBSIDIAN**

- **Open Bugs** — atualizar o HIGH histórico com a recuperação medida, mantendo separadas as lacunas de cobertura e os picos residuais.
- **KB-0087 / KB-0089** — acrescentar a releitura de setembro, corrigindo a população diária e delimitando a evidência pós-correções.
- **Revisões Astra — diagnóstico de latência do Shadow Lab** — registrar janela analítica, limites do item 6 e proposta de observabilidade.
- **Diário — 2026-10-01** — registrar esta revisão retrospectiva; preservar o diário de 11/09 como registro datado.