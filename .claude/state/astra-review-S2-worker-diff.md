**RESUMO**

**REQUEST_CHANGES — eu ainda não reportaria DONE.** Dos quatro must-fix anteriores: a proteção transacional está bem encaminhada; a interrupção da série agora censura; o hold alcança followers; **a elegibilidade histórica continua sem prova**.

Revisei como `code-reviewer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado por mim. Nenhum commit.

**TESTES**

Executei com caches e escrita de bytecode desabilitados:

| Comando | Saída real |
|---|---|
| `uv run pytest services/strategy-worker/tests/test_outcome_walk.py services/strategy-worker/tests/test_entry_plan.py services/strategy-worker/tests/test_funding.py services/strategy-worker/tests/test_identity_and_slots.py -q` | `62 passed in 1.12s` |
| `uv run pytest services/strategy-worker/tests/test_consumer_supervision.py -q` | `3 passed in 2.39s` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run python infra/scripts/check_file_size.py` | `scanned 173 files; 0 over budget, 0 grandfathered` |
| `uv run ruff format --check .` | `3 files would be reformatted, 462 files already formatted` |

A formatação falhou em três páginas do Obsidian fora do diff S2: `Exchange Adapters`, `Execution Engine` e `Strategies`.

Também executei sondas sintéticas em memória com `uv run python -`. **Não executei integração PostgreSQL/Redis, build ou prova operacional de 30 minutos.** As sondas não substituem esses testes.

**MUST-FIX**

1. **HIGH — o limite de 300 segundos não comprova elegibilidade histórica.**  
   [decide.py:88](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:88) admite a barra pelo atraso; [context.py:73](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/context.py:73) usa o estado corrente do mercado.

   **Cenário:** barra falsa fecha às 12:15 com mercado inelegível; refresh inclui o mercado às 12:16; evento chega às 12:17. O atraso de 120 segundos passa e rearma indevidamente. Estar abaixo do período de refresh não significa permanecer no mesmo ciclo. O must-fix anterior 4 **não foi resolvido**. É necessária evidência válida no fechamento, ou `unavailable` quando ela faltar.

2. **HIGH — timestamps de extremos continuam inventados.**  
   [walker.py:271](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:271) atribui a abertura da barra ao máximo/mínimo; [excursions.py:126](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:126) publica esse timestamp quando os limites do **valor** coincidem.

   **Cenário:** máxima 101 ocorreu às 12:01:40; só sabemos OHLC da barra 12:01. O código registra `mfe_ts=12:01:00`. Conhecer o valor não determina seu instante. O teste [test_outcome_walk.py:226](C:/dev/project-hunter/services/strategy-worker/tests/test_outcome_walk.py:226) consolida justamente essa afirmação indevida. Timestamps precisam de nulidade independente dos valores; a janela conhecida pertence aos metadados.

3. **HIGH — censura transforma excursões parciais em totais exatas.**  
   [excursions.py:92](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:92) inicia os limites superiores iguais aos inferiores e não trata a cauda desconhecida de um acompanhamento censurado.

   **Cenário reproduzido:** entrada 100; primeira barra conhecida high 101/low 99,5; depois a série desaparece. Após censura, obtive:
   ```text
   mfe=1, mae=0.5, ambiguous=False
   coverage={'bars_known': 1, 'bars_total': 1}
   ```
   A barra ausente poderia conter qualquer dos extremos antes da saída. Preserve os valores conhecidos em `*_complete_bars`; não os apresente como excursões totais determinadas nem como cobertura integral.

4. **HIGH — gap favorável confunde preço de saída convencionado com preço observado.**  
   [walker.py:236](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:236) limita corretamente a saída ao alvo, mas [excursions.py:94](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:94) usa esse preço limitado para medir a excursão.

   **Cenário reproduzido:** entrada 100, alvo 102, próxima abertura 105. A saída hipotética deve continuar em 102, porém o preço observado na abertura é 105. Obtive `bounds.mfe=[2,2], ambiguous=False`. Guarde separadamente a abertura observada e a base sintética de saída; não limitar o crédito financeiro é diferente de medir o extremo de mercado.

5. **HIGH — o funding pode omitir cobrança conhecida e cobrar depois de uma saída intrabar.**  
   Há dois cenários distintos:

   **Cadência:** [funding.py:105](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:105) calcula apenas os instantes da grade estimada. Histórico às 00h, 08h, 16h e 20h; acompanhamento das 17h às 21h. A moda permanece 8h e a cobrança conhecida das 20h desaparece. Reproduzi `per_unit=0, settlements=0`. Liquidações efetivamente presentes dentro da janela não podem ser descartadas; cadência inconsistente deve produzir incerteza explícita.

   **Instante de saída:** [walker.py:258](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:258) usa o fechamento como barreira conservadora do toque; [settle.py:66](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:66) reutiliza essa barreira como instante financeiro exato. Entrada 15:59, stop dentro dessa barra, funding às 16:00: reproduzi cobrança de `0.0100`. A barreira de rearme não comprova permanência até a liquidação. Separe janela de saída, barreira e elegibilidade ao funding.

6. **HIGH — o worker não verifica se executa o código congelado.**  
   [repo.py:118](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/repo.py:118) resolve a implementação pelo registry e apenas transporta o `code_ref` armazenado.

   **Cenário:** ativar v1 com hash A; publicar alteração na calculadora mantendo a chave v1; reiniciar. O worker executa B e grava proveniência A. A verificação no script de ativação não protege um restart comum. Recuse versões cujo código disponível não corresponda ao congelado. Inclua também a identidade do modelo de outcome: o hash atual cobre somente `strategies/**`, conforme [activation.py:68](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/activation.py:68).

7. **MEDIUM — stream ocioso saudável continua ficando vermelho em `/ready`.**  
   [consumer.py:157](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:157) atualiza saúde somente quando recebe mensagem; [health.py:79](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/health.py:79) considera a ausência desse carimbo um consumidor parado.

   **Cenário:** Redis responde normalmente, mas não há candles durante seis minutos. O gerador continua fazendo leituras vazias, sem entregar uma iteração ao chamador, e `/ready` fica falso. Reproduzi esse resultado. Diferencie atividade do laço de chegada de dados; reduzir `block_ms` não resolve essa segunda questão.

8. **MEDIUM — a blocklist só filtra os símbolos acrescentados pelo hold.**  
   [universe.py:216](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:216) filtra `extra`, mas devolve `monitored` integralmente.

   **Cenário:** follower reinicia com uma nova blocklist e recebe um snapshot anterior que ainda contém o símbolo bloqueado. Ele permanece na coleta porque já veio em `monitored`. Aplique a exclusão ao conjunto final, inclusive no fallback. O teste atual cobre somente o símbolo presente exclusivamente no hold: [test_universe_tracking_hold.py:175](C:/dev/project-hunter/services/market-worker/tests/test_universe_tracking_hold.py:175).

**NICE-TO-HAVE**

- **Sim, abriria tarefa própria para o default de `consume()`.** Os `5000 ms` em [consume.py:54](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:54) conflitam com o orçamento de socket de 5 segundos em [redis.py:54](C:/dev/project-hunter/packages/core/hunter_core/redis.py:54). Teste com Redis real, stream vazio e configuração padrão, além de reconexão.
- Alinhar a prioridade documentada em [.claude/state/notes-S2.md](C:/dev/project-hunter/.claude/state/notes-S2.md) com [walker.py:238](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:238): a implementação coloca invalidação antes do horizonte.
- Acrescentar teste de atraso no flush: contexto completo pelo Redis, mas barra de encerramento ainda ausente no Postgres. Mesmo avançando primeiro, [decide.py:124](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:124) pode encontrar acompanhamento ainda aberto e consumir o fechamento falso sem rearme.

**O QUE EU FARIA DIFERENTE**

Separaria explicitamente **preço observado, preço sintético, instante comprovado, janela temporal e barreira de rearme**. As falhas de excursões e funding vêm de reutilizar um desses conceitos como se comprovasse outro.

Antes de DONE, exigiria regressões dos cenários acima, integração das corridas confirmação/polling e a prova operacional. Também manteria pendente a evidência de preservação das fontes após retenção, exigida pelo plano.

**CONCORDO COM**

- **Custos:** a conta reproduziu `P_entry=100.0600`, `P_exit=98.9406`, numerador `-1.19900024`, risco `1.0600`. Taxas nos dois lados e funding assinado estão corretos na fórmula de [pricing.py:73](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:73). Separar `r_ex_funding` de `r_multiple=NULL` também está correto; o problema está em determinar o funding.
- **Walker:** abertura antes de intrabar e stop antes de alvo seguem a convenção; contiguidade e `finished` impedem avanço sobre buracos e reabertura no fold, em [walker.py:232](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:232) e [walker.py:323](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:323).
- **Slots e confirmação:** criação com conflito tratado, lock, liberação pelo sinal esperado e atualização restrita a outcomes abertos são boas proteções: [slots.py:80](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/slots.py:80), [slots.py:147](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/slots.py:147), [tracking_repo.py:165](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/tracking_repo.py:165). Não encontrei entrada retroativa no fluxo normal de [confirm.py:63](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/confirm.py:63), assumindo relógio confiável.
- **Interrupção da série:** agora termina censurada mesmo sem velas posteriores. A sonda, com round-trip JSON do prazo, produziu `active → censored`. O caminho está em [outcomes.py:210](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/outcomes.py:210) e [outcomes.py:236](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/outcomes.py:236).
- **Hold:** a união antes do sharding cobre líder/follower e a consulta preserva múltiplas versões sem escrever `is_monitored`: [universe.py:280](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:280), [universe_repo.py:145](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:145). Ressalva: filtrar a blocklist no resultado completo.
- **Isolamento:** persistência em stream próprio com `research_only` está explícita em [persist.py:88](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:88) e [record.py:197](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:197).

**OBSIDIAN**

- **Strategies** — registrar a pendência de elegibilidade histórica e a verificação do código congelado.
- **Strategy Performance** — distinguir extremos parciais, timestamps desconhecidos, gaps e incerteza de funding.
- **Workers** — documentar confirmação pós-commit, censura durável e saúde do consumidor ocioso.
- **Market Collector** — atualizar o hold nos shards e a precedência da blocklist sobre o conjunto completo.
- **Revisões Astra — S2** — registrar este parecer, evidências executadas e bloqueios restantes.